#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Game-aware dataset utilities for the autonomous L3-PURE self-play loop.

The tool consumes only Jass self-play records and an aligned ``JSM1`` or
``JSM2`` sidecar
emitted by ``jass --gen-data-wdl --sample-meta-out``.  It has five operations:

``merge``
    Merge independent shards while namespacing game/opening identifiers.

``mix``
    Build an exact-size, deterministic weighted mixture of aligned JNNW/metadata
    corpora.  Sampling is uniform at record level, while opening identifiers
    are preserved across sources so a subsequent ``split`` still assigns every
    occurrence of a paired opening to the same fold.

``split``
    Put complete opening groups (including ``--pair-openings`` repetitions) in
    either train or holdout, then write train rows followed by holdout rows.

``mine``
    Build the next generation's moving conversion frontier.  Candidates are
    positions reached by the lineage itself where a material advantage was
    either lost/drawn (primary) or converted (small calibration share).  The
    only outcome used for selection is the actual terminal WDL already present
    in JNNW.  Output seed records have score and WDL zeroed, so no target can
    leak into the next game; their continuations must earn a fresh terminal WDL.

``profile``
    Publish distribution diagnostics for one merged self-play corpus: realised
    opening/game diversity, unique positions, phase/material coverage and a
    record-level conversion diagnostic.  The latter is explicitly not a gate:
    records from the same game are correlated.

This is deliberately not an oracle miner: no Scan, deep relabel, master game,
fixed gymnasium or external teacher is accepted as input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

JNNW_MAGIC = b"JNNW"
JNNW_REC = 38
JSM1_MAGIC = b"JSM1"
JSM2_MAGIC = b"JSM2"
JSM1_STRUCT = struct.Struct("<QQB")
JSM2_STRUCT = struct.Struct("<QQBHHHbB")
META_MAGIC = JSM1_MAGIC  # Backward-compatible aliases used by older callers.
META_REC = JSM1_STRUCT.size


@dataclass(frozen=True)
class MetaSchema:
    magic: bytes
    record: struct.Struct

    @property
    def name(self) -> str:
        return self.magic.decode("ascii")


JSM1_SCHEMA = MetaSchema(JSM1_MAGIC, JSM1_STRUCT)
JSM2_SCHEMA = MetaSchema(JSM2_MAGIC, JSM2_STRUCT)
META_SCHEMAS = {schema.magic: schema for schema in (JSM1_SCHEMA, JSM2_SCHEMA)}



def _load_canary():
    """`assert_corpus_wdl` vit sous `jobs/tools`, qui n'est pas un package.
    On l'importe par chemin plutôt que d'en dupliquer les seuils : une garde
    définie à deux endroits finit toujours par diverger."""
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "jobs" / "tools" / "assert_corpus_wdl.py"
    spec = importlib.util.spec_from_file_location("assert_corpus_wdl", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"canari WDL introuvable à {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wdl_report_from_counts(counts: dict[int, int], args) -> dict | None:
    if getattr(args, "no_wdl_check", False):
        return None
    canary = _load_canary()
    unexpected = set(counts) - {-1, 0, 1}
    if unexpected:
        raise ValueError(f"étiquettes WDL hors domaine {sorted(unexpected)}")

    def opt(name, fallback):
        # argparse laisse None quand l'option n'est pas passée ; `getattr` seul
        # renverrait ce None et écraserait le défaut du canari.
        value = getattr(args, name, None)
        return fallback if value is None else value

    return canary.evaluate(
        counts,
        min_draw_share=opt("wdl_min_draw_share", canary.DEFAULT_MIN_DRAW_SHARE),
        max_draw_share=opt("wdl_max_draw_share", canary.DEFAULT_MAX_DRAW_SHARE),
        max_side_skew=opt("wdl_max_side_skew", canary.DEFAULT_MAX_SIDE_SKEW),
    )


def _wdl_report(records, args) -> dict | None:
    if getattr(args, "no_wdl_check", False):
        return None
    canary = _load_canary()
    return _wdl_report_from_counts(canary.histogram_from_records(records), args)


@dataclass(frozen=True)
class Meta:
    game_id: int
    opening_id: int
    seeded: int
    ply: int | None = None
    game_plies: int | None = None
    last_eps_ply: int | None = None
    game_result: int | None = None  # WHITE POV; JNNW WDL is side-to-move POV.
    flags: int | None = None


def _meta_schema_for_rows(rows: list[Meta]) -> MetaSchema:
    extended = [row.ply is not None for row in rows]
    if any(extended) and not all(extended):
        raise ValueError("cannot mix JSM1 and JSM2 metadata rows")
    return JSM2_SCHEMA if any(extended) else JSM1_SCHEMA


def _validate_meta(row: Meta, schema: MetaSchema, *, context: str = "metadata") -> None:
    if row.seeded not in (0, 1):
        raise ValueError(f"{context}: seeded {row.seeded} outside {{0,1}}")
    if not (0 <= row.game_id < (1 << 64) and 0 <= row.opening_id < (1 << 64)):
        raise ValueError(f"{context}: game/opening id outside u64")
    if schema is JSM1_SCHEMA:
        if any(value is not None for value in (
            row.ply, row.game_plies, row.last_eps_ply, row.game_result, row.flags
        )):
            raise ValueError(f"{context}: extended fields cannot be encoded as JSM1")
        return
    values = (row.ply, row.game_plies, row.last_eps_ply, row.game_result, row.flags)
    if any(value is None for value in values):
        raise ValueError(f"{context}: incomplete JSM2 record")
    assert row.ply is not None and row.game_plies is not None
    assert row.last_eps_ply is not None and row.game_result is not None
    assert row.flags is not None
    if not (0 <= row.ply <= 0xFFFF and 0 <= row.game_plies <= 0xFFFF):
        raise ValueError(f"{context}: ply fields outside u16")
    if not (0 <= row.last_eps_ply <= 0xFFFF):
        raise ValueError(f"{context}: last_eps_ply outside u16")
    if row.game_result not in (-1, 0, 1):
        raise ValueError(f"{context}: game_result outside {{-1,0,1}}")
    if not (0 <= row.flags <= 0xFF) or row.flags & ~0x07:
        raise ValueError(f"{context}: flags use reserved bits")
    if row.ply >= row.game_plies:
        raise ValueError(f"{context}: ply {row.ply} is not below game_plies {row.game_plies}")


def _decode_meta(raw: bytes, schema: MetaSchema, *, context: str = "metadata") -> Meta:
    row = Meta(*schema.record.unpack(raw))
    _validate_meta(row, schema, context=context)
    return row


def _encode_meta(row: Meta, schema: MetaSchema, *, context: str = "metadata") -> bytes:
    _validate_meta(row, schema, context=context)
    if schema is JSM1_SCHEMA:
        return schema.record.pack(row.game_id, row.opening_id, row.seeded)
    return schema.record.pack(
        row.game_id,
        row.opening_id,
        row.seeded,
        row.ply,
        row.game_plies,
        row.last_eps_ply,
        row.game_result,
        row.flags,
    )


def _meta_file_info(path: Path) -> tuple[MetaSchema, int]:
    with path.open("rb") as stream:
        header = stream.read(8)
    if len(header) != 8 or header[:4] not in META_SCHEMAS:
        found = header[:4] if len(header) >= 4 else header
        raise ValueError(f"{path}: expected JSM1 or JSM2 header, found {found!r}")
    schema = META_SCHEMAS[header[:4]]
    count = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + count * schema.record.size
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"{path}: size {actual} != {expected} for {count} {schema.name} records")
    return schema, count


@dataclass(frozen=True)
class Candidate:
    record: bytes
    meta: Meta
    kind: str
    margin: int
    pieces: int


def _read_counted(path: Path, magic: bytes, record_size: int) -> tuple[int, bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != magic:
        raise ValueError(f"{path}: expected {magic.decode('ascii')} header")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * record_size
    if len(raw) != expected:
        raise ValueError(f"{path}: size {len(raw)} != {expected} for {count} records")
    return count, raw[8:]


def read_pair(data_path: Path, meta_path: Path) -> tuple[list[bytes], list[Meta]]:
    n_data, data = _read_counted(data_path, JNNW_MAGIC, JNNW_REC)
    schema, n_meta = _meta_file_info(meta_path)
    if n_data != n_meta:
        raise ValueError(f"data/meta count mismatch: {n_data} != {n_meta}")
    records = [data[i * JNNW_REC:(i + 1) * JNNW_REC] for i in range(n_data)]
    with meta_path.open("rb") as stream:
        stream.seek(8)
        rows = [
            _decode_meta(
                stream.read(schema.record.size), schema,
                context=f"{meta_path}: record {index}",
            )
            for index in range(n_meta)
        ]
    return records, rows


def iter_pair(data_path: Path, meta_path: Path):
    """Iterate an aligned JNNW/JSM1-or-JSM2 pair without materialising it."""
    n_data = _counted_file_count(data_path, JNNW_MAGIC, JNNW_REC)
    schema, n_meta = _meta_file_info(meta_path)
    if n_data != n_meta:
        raise ValueError(f"data/meta count mismatch: {n_data} != {n_meta}")
    with data_path.open("rb") as data_in, meta_path.open("rb") as meta_in:
        data_in.seek(8)
        meta_in.seek(8)
        for index in range(n_data):
            record = data_in.read(JNNW_REC)
            meta_raw = meta_in.read(schema.record.size)
            if len(record) != JNNW_REC or len(meta_raw) != schema.record.size:
                raise ValueError(f"aligned pair truncated at record {index}")
            yield index, record, _decode_meta(
                meta_raw, schema, context=f"{meta_path}: record {index}"
            )


def write_pair(data_path: Path, meta_path: Path,
               records: list[bytes], rows: list[Meta]) -> None:
    if len(records) != len(rows):
        raise ValueError("data/meta output count mismatch")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    count = len(records)
    schema = _meta_schema_for_rows(rows)
    data_path.write_bytes(JNNW_MAGIC + struct.pack("<I", count) + b"".join(records))
    meta_body = b"".join(
        _encode_meta(row, schema, context=f"output metadata record {index}")
        for index, row in enumerate(rows)
    )
    meta_path.write_bytes(schema.magic + struct.pack("<I", count) + meta_body)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_pair_atomic(
    data_path: Path,
    meta_path: Path,
    records: list[bytes],
    rows: list[Meta],
) -> None:
    if len(records) != len(rows):
        raise ValueError("data/meta output count mismatch")
    count = len(records)
    schema = _meta_schema_for_rows(rows)
    data_payload = JNNW_MAGIC + struct.pack("<I", count) + b"".join(records)
    meta_body = b"".join(
        _encode_meta(row, schema, context=f"output metadata record {index}")
        for index, row in enumerate(rows)
    )
    _atomic_write_bytes(data_path, data_payload)
    _atomic_write_bytes(
        meta_path, schema.magic + struct.pack("<I", count) + meta_body
    )


def _manifest(path: str | None, payload: dict) -> None:
    if path:
        Path(path).write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def do_merge(args: argparse.Namespace) -> int:
    source_counts: Counter = Counter()
    wdl_counts: Counter = Counter()
    shard_rows = []
    renamespace_nested = bool(getattr(args, "renamespace_nested", False))
    sources = []
    meta_schema: MetaSchema | None = None
    total = 0
    for shard_index, (data_name, meta_name) in enumerate(args.pair, start=1):
        if shard_index >= (1 << 16):
            raise ValueError("too many shards for 16-bit namespace")
        data_path, meta_path = Path(data_name), Path(meta_name)
        count = _counted_file_count(data_path, JNNW_MAGIC, JNNW_REC)
        source_schema, meta_count = _meta_file_info(meta_path)
        if meta_count != count:
            raise ValueError(f"{data_name}: data/meta count mismatch")
        if meta_schema is None:
            meta_schema = source_schema
        elif source_schema is not meta_schema:
            raise ValueError("merge inputs must all use the same sidecar schema")
        sources.append((shard_index, data_name, meta_name, data_path, meta_path, count))
        total += count
    assert meta_schema is not None

    out_data, out_meta = Path(args.out_data), Path(args.out_meta)
    out_data.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    try:
        with data_tmp.open("wb") as data_out, meta_tmp.open("wb") as meta_out:
            data_out.write(JNNW_MAGIC + struct.pack("<I", total))
            meta_out.write(meta_schema.magic + struct.pack("<I", total))
            for (
                shard_index,
                data_name,
                meta_name,
                data_path,
                meta_path,
                count,
            ) in sources:
                prefix = shard_index << 48
                game_namespace: dict[int, int] = {}
                opening_namespace: dict[int, int] = {}
                for _, record, row in iter_pair(data_path, meta_path):
                    if renamespace_nested:
                        game_id = game_namespace.setdefault(
                            row.game_id, len(game_namespace)
                        )
                        opening_id = opening_namespace.setdefault(
                            row.opening_id, len(opening_namespace)
                        )
                    else:
                        game_id = row.game_id
                        opening_id = row.opening_id
                    if game_id >= (1 << 48) or opening_id >= (1 << 48):
                        raise ValueError(
                            "local game/opening id exceeds 48-bit namespace"
                        )
                    data_out.write(record)
                    meta_out.write(_encode_meta(
                        replace(
                            row,
                            game_id=prefix | game_id,
                            opening_id=prefix | opening_id,
                        ),
                        meta_schema,
                        context=f"merge output record from {meta_name}",
                    ))
                    wdl_counts[struct.unpack_from("<b", record, 37)[0]] += 1
                    source_counts[
                        "frontier" if row.seeded else "standard"
                    ] += 1
                shard_rows.append({
                    "data": data_name,
                    "meta": meta_name,
                    "records": count,
                    "nested_namespace_remapped": renamespace_nested,
                    "games": len(game_namespace) if renamespace_nested else None,
                    "openings": (
                        len(opening_namespace) if renamespace_nested else None
                    ),
                })
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
    finally:
        for temporary in (data_tmp, meta_tmp):
            if temporary.exists():
                temporary.unlink()

    # Canari WDL au point de passage. Tous les templates L3 fusionnent leurs
    # shards ici, donc la garde s'applique sans qu'aucun d'eux ait à y penser.
    # Elle porte sur les DONNÉES : elle aurait vu le défaut de racine nulle
    # (4,8 % de nulles au lieu de 20,3 %) sans rien savoir de sa cause.
    # Les corpus dont la distribution est légitimement asymétrique — la lignée
    # IMBALANCE2 part d'un avantage matériel — passent un plancher explicite.
    wdl = _wdl_report_from_counts(dict(wdl_counts), args)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "merge",
        "records": total,
        "sidecar_schema": {
            "magic": meta_schema.name,
            "record_size": meta_schema.record.size,
        },
        "shards": shard_rows,
        "source_records": dict(sorted(source_counts.items())),
        "wdl_canary": wdl,
    })
    if wdl is not None and not wdl["ok"]:
        for problem in wdl["problems"]:
            print(f"CORPUS_WDL_ABORT: {problem}", file=sys.stderr)
        raise SystemExit(6)
    return 0


def _counted_file_count(path: Path, magic: bytes, record_size: int) -> int:
    with path.open("rb") as stream:
        header = stream.read(8)
    if len(header) != 8 or header[:4] != magic:
        raise ValueError(f"{path}: expected {magic.decode('ascii')} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + count * record_size
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"{path}: size {actual} != {expected} for {count} records")
    return count


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9 & ((1 << 64) - 1)
    value = (value ^ (value >> 27)) * 0x94D049BB133111EB & ((1 << 64) - 1)
    return value ^ (value >> 31)


def _sample_indices(population: int, sample: int, seed: int) -> set[int]:
    """Return an exact deterministic sample using Floyd's O(sample) algorithm."""
    if not 0 <= sample <= population:
        raise ValueError(f"sample {sample} outside population {population}")
    selected: set[int] = set()
    state = seed & ((1 << 64) - 1)

    def randbelow(bound: int) -> int:
        nonlocal state
        if bound <= 0:
            raise ValueError("randbelow bound must be positive")
        modulus = 1 << 64
        limit = modulus - modulus % bound
        while True:
            state = _splitmix64(state)
            if state < limit:
                return state % bound

    for upper in range(population - sample, population):
        candidate = randbelow(upper + 1)
        selected.add(upper if candidate in selected else candidate)
    if len(selected) != sample:
        raise AssertionError("deterministic sampler returned the wrong cardinality")
    return selected


def _weighted_quotas(total: int, weights: list[int]) -> list[int]:
    if total < 1:
        raise ValueError("--target-records must be positive")
    if not weights or any(weight <= 0 for weight in weights):
        raise ValueError("mix weights must be positive integers")
    denominator = sum(weights)
    quotas = [total * weight // denominator for weight in weights]
    missing = total - sum(quotas)
    order = sorted(
        range(len(weights)),
        key=lambda index: (-(total * weights[index] % denominator), index),
    )
    for index in order[:missing]:
        quotas[index] += 1
    return quotas


def _source_mix_seed(seed: int, label: str, index: int) -> int:
    payload = struct.pack("<QQ", seed & ((1 << 64) - 1), index)
    payload += label.encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little")


def do_mix(args: argparse.Namespace) -> int:
    """Create a memory-bounded exact weighted mix while preserving JSM alignment."""
    namespace_openings = bool(getattr(args, "namespace_openings", False))
    sources = []
    meta_schema: MetaSchema | None = None
    labels: set[str] = set()
    for source_index, spec in enumerate(args.source, start=1):
        label, data_name, meta_name, weight_text = spec
        if label in labels:
            raise ValueError(f"duplicate mix source label: {label}")
        labels.add(label)
        try:
            weight = int(weight_text)
        except ValueError as exc:
            raise ValueError(f"{label}: invalid integer weight {weight_text!r}") from exc
        data_path, meta_path = Path(data_name), Path(meta_name)
        data_count = _counted_file_count(data_path, JNNW_MAGIC, JNNW_REC)
        source_schema, meta_count = _meta_file_info(meta_path)
        if data_count != meta_count:
            raise ValueError(f"{label}: data/meta count mismatch: {data_count} != {meta_count}")
        if meta_schema is None:
            meta_schema = source_schema
        elif source_schema is not meta_schema:
            raise ValueError("mix inputs must all use the same sidecar schema")
        sources.append({
            "index": source_index,
            "label": label,
            "data": data_path,
            "meta": meta_path,
            "weight": weight,
            "records": data_count,
        })
    assert meta_schema is not None

    target = args.target_records
    quotas = _weighted_quotas(target, [source["weight"] for source in sources])
    for source, quota in zip(sources, quotas):
        if quota > source["records"]:
            raise ValueError(
                f"{source['label']}: quota {quota} exceeds {source['records']} records"
            )
        source["quota"] = quota

    out_data, out_meta = Path(args.out_data), Path(args.out_meta)
    out_data.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    data_header = JNNW_MAGIC + struct.pack("<I", target)
    meta_header = meta_schema.magic + struct.pack("<I", target)
    output_data_hash = hashlib.sha256(data_header)
    output_meta_hash = hashlib.sha256(meta_header)
    source_manifests = []
    opening_sets: dict[str, set[int]] = {}
    selected_total = 0

    try:
        with data_tmp.open("wb") as data_out, meta_tmp.open("wb") as meta_out:
            data_out.write(data_header)
            meta_out.write(meta_header)
            for source, quota in zip(sources, quotas):
                count = source["records"]
                sample_size = min(quota, count - quota)
                sampled = _sample_indices(
                    count,
                    sample_size,
                    _source_mix_seed(args.seed, source["label"], source["index"]),
                )
                sampled_are_included = quota <= count - quota
                data_hash = hashlib.sha256()
                meta_hash = hashlib.sha256()
                source_openings: set[int] = set()
                selected_openings: set[int] = set()
                game_namespace: dict[int, int] = {}
                opening_namespace: dict[int, int] = {}
                selected = 0
                with source["data"].open("rb") as data_in, source["meta"].open("rb") as meta_in:
                    data_source_header = data_in.read(8)
                    meta_source_header = meta_in.read(8)
                    data_hash.update(data_source_header)
                    meta_hash.update(meta_source_header)
                    for row_index in range(count):
                        record = data_in.read(JNNW_REC)
                        meta_raw = meta_in.read(meta_schema.record.size)
                        if len(record) != JNNW_REC or len(meta_raw) != meta_schema.record.size:
                            raise ValueError(f"{source['label']}: truncated aligned pair")
                        data_hash.update(record)
                        meta_hash.update(meta_raw)
                        row = _decode_meta(
                            meta_raw,
                            meta_schema,
                            context=f"{source['meta']}: record {row_index}",
                        )
                        game_id, opening_id = row.game_id, row.opening_id
                        source_openings.add(opening_id)
                        chosen = row_index in sampled
                        if not sampled_are_included:
                            chosen = not chosen
                        if not chosen:
                            continue
                        local_game = game_namespace.setdefault(game_id, len(game_namespace))
                        if local_game >= (1 << 56):
                            raise ValueError(f"{source['label']}: too many games to namespace")
                        namespaced_game = source["index"] << 56 | local_game
                        output_opening = opening_id
                        if namespace_openings:
                            local_opening = opening_namespace.setdefault(
                                opening_id, len(opening_namespace)
                            )
                            if local_opening >= (1 << 56):
                                raise ValueError(
                                    f"{source['label']}: too many openings to namespace"
                                )
                            output_opening = source["index"] << 56 | local_opening
                        output_meta = _encode_meta(
                            replace(
                                row,
                                game_id=namespaced_game,
                                opening_id=output_opening,
                            ),
                            meta_schema,
                            context=f"mix output record from {source['label']}",
                        )
                        data_out.write(record)
                        meta_out.write(output_meta)
                        output_data_hash.update(record)
                        output_meta_hash.update(output_meta)
                        selected_openings.add(opening_id)
                        selected += 1
                if selected != quota:
                    raise AssertionError(
                        f"{source['label']}: selected {selected} records, expected {quota}"
                    )
                selected_total += selected
                opening_sets[source["label"]] = source_openings
                source_manifests.append({
                    "label": source["label"],
                    "data": str(source["data"]),
                    "meta": str(source["meta"]),
                    "weight": source["weight"],
                    "input_records": count,
                    "selected_records": selected,
                    "selected_fraction": selected / count if count else 0.0,
                    "input_data_sha256": data_hash.hexdigest(),
                    "input_meta_sha256": meta_hash.hexdigest(),
                    "input_openings": len(source_openings),
                    "selected_openings": len(selected_openings),
                    "output_games": len(game_namespace),
                })
        if selected_total != target:
            raise AssertionError(f"mix selected {selected_total} records, expected {target}")
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
    finally:
        if data_tmp.exists():
            data_tmp.unlink()
        if meta_tmp.exists():
            meta_tmp.unlink()

    overlaps = {}
    for left_index, left in enumerate(sources):
        for right in sources[left_index + 1:]:
            key = f"{left['label']}__{right['label']}"
            overlaps[key] = len(opening_sets[left["label"]] & opening_sets[right["label"]])
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "weighted_aligned_mix",
        "selection": "exact_uniform_record_sample_splitmix64_floyd",
        "seed": args.seed,
        "target_records": target,
        "records": selected_total,
        "sidecar_schema": {
            "magic": meta_schema.name,
            "record_size": meta_schema.record.size,
        },
        "sources": source_manifests,
        "opening_id_policy": (
            "source_namespaced_for_independent_temporal_corpora"
            if namespace_openings
            else "preserved_across_sources_for_common_holdout_fold"
        ),
        "game_id_policy": "source_namespaced",
        "source_opening_id_overlaps": overlaps,
        "subsequent_split_unit": "opening_id",
        "out_data_sha256": output_data_hash.hexdigest(),
        "out_meta_sha256": output_meta_hash.hexdigest(),
        "external_teacher_inputs": 0,
    })
    return 0


def _opening_fold(opening_id: int, seed: int, mod: int) -> int:
    payload = struct.pack("<QQ", opening_id, seed & ((1 << 64) - 1))
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little") % mod


def do_split(args: argparse.Namespace) -> int:
    if args.holdout_mod < 2:
        raise ValueError("--holdout-mod must be >= 2")
    data_path, meta_path = Path(args.data), Path(args.meta)
    total = _counted_file_count(data_path, JNNW_MAGIC, JNNW_REC)
    meta_schema, meta_count = _meta_file_info(meta_path)
    if meta_count != total:
        raise ValueError("data/meta count mismatch")

    # First pass: determine the fold of every opening and exact output counts.
    # Only the opening-id set is retained, so 40M-record catalogues remain
    # practical on HOME.
    fold_by_opening: dict[int, bool] = {}
    train_count = 0
    holdout_count = 0
    with meta_path.open("rb") as meta_in:
        meta_in.seek(8)
        for index in range(total):
            raw = meta_in.read(meta_schema.record.size)
            if len(raw) != meta_schema.record.size:
                raise ValueError(f"metadata truncated at record {index}")
            opening_id = _decode_meta(
                raw, meta_schema, context=f"{meta_path}: record {index}"
            ).opening_id
            hold = fold_by_opening.setdefault(
                opening_id,
                _opening_fold(opening_id, args.seed, args.holdout_mod) == 0,
            )
            if hold:
                holdout_count += 1
            else:
                train_count += 1

    out_data, out_meta = Path(args.out_data), Path(args.out_meta)
    out_data.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    hold_data_tmp = out_data.with_name(out_data.name + ".hold.tmp")
    hold_meta_tmp = out_meta.with_name(out_meta.name + ".hold.tmp")

    # Second pass: write train directly, spool holdout, then append the spool.
    try:
        with (
            data_tmp.open("wb") as train_data,
            meta_tmp.open("wb") as train_meta,
            hold_data_tmp.open("wb") as hold_data,
            hold_meta_tmp.open("wb") as hold_meta,
        ):
            train_data.write(JNNW_MAGIC + struct.pack("<I", total))
            train_meta.write(meta_schema.magic + struct.pack("<I", total))
            for _, record, row in iter_pair(data_path, meta_path):
                raw_meta = _encode_meta(row, meta_schema)
                if fold_by_opening[row.opening_id]:
                    hold_data.write(record)
                    hold_meta.write(raw_meta)
                else:
                    train_data.write(record)
                    train_meta.write(raw_meta)
            hold_data.flush()
            hold_meta.flush()
            with hold_data_tmp.open("rb") as source:
                shutil.copyfileobj(source, train_data, 1 << 20)
            with hold_meta_tmp.open("rb") as source:
                shutil.copyfileobj(source, train_meta, 1 << 20)
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
    finally:
        for temporary in (data_tmp, meta_tmp, hold_data_tmp, hold_meta_tmp):
            if temporary.exists():
                temporary.unlink()

    hold_openings = sum(fold_by_opening.values())
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "split",
        "split_unit": "opening_id",
        "holdout_mod": args.holdout_mod,
        "seed": args.seed,
        "records": total,
        "sidecar_schema": {
            "magic": meta_schema.name,
            "record_size": meta_schema.record.size,
        },
        "train_records": train_count,
        "holdout_records": holdout_count,
        "train_openings": len(fold_by_opening) - hold_openings,
        "holdout_openings": hold_openings,
        "tail_is_holdout": True,
    })
    return 0


def _material(record: bytes) -> tuple[str | None, int, int]:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    white = wm.bit_count() + 3 * wk.bit_count()
    black = bm.bit_count() + 3 * bk.bit_count()
    pieces = wm.bit_count() + wk.bit_count() + bm.bit_count() + bk.bit_count()
    if white > black:
        return "W", white - black, pieces
    if black > white:
        return "B", black - white, pieces
    return None, 0, pieces


def _winner(record: bytes) -> str | None:
    stm = record[32]
    wdl = struct.unpack_from("<b", record, 37)[0]
    if wdl == 0:
        return None
    stm_side = "W" if stm == 0 else "B"
    if wdl > 0:
        return stm_side
    return "B" if stm_side == "W" else "W"


def _candidate_hash(candidate: Candidate, seed: int) -> bytes:
    return hashlib.blake2b(
        candidate.record[:33]
        + struct.pack("<QQQ", candidate.meta.game_id, candidate.meta.opening_id, seed),
        digest_size=16,
    ).digest()


def _piece_band(pieces: int) -> str:
    if pieces <= 10:
        return "deep_endgame"
    if pieces <= 16:
        return "endgame"
    return "late_midgame"


def _phase_band(pieces: int) -> str:
    if pieces >= 30:
        return "opening"
    if pieces >= 22:
        return "midgame"
    if pieces >= 15:
        return "late_midgame"
    if pieces >= 8:
        return "endgame"
    return "deep_endgame"


def _material_stratum(margin: int) -> str:
    if margin == 0:
        return "p4_equal"
    if margin == 1:
        return "p3_thin"
    if margin <= 3:
        return "p2_medium"
    return "p1_clear"


def _count_summary(values: Counter) -> dict:
    if not values:
        return {"min": 0, "max": 0, "mean": 0.0}
    counts = list(values.values())
    return {
        "min": min(counts),
        "max": max(counts),
        "mean": sum(counts) / len(counts),
    }


def do_profile(args: argparse.Namespace) -> int:
    records, rows = read_pair(Path(args.data), Path(args.meta))
    unique_positions: set[bytes] = set()
    unique_by_stratum: dict[str, set[bytes]] = defaultdict(set)
    records_by_game: Counter = Counter()
    records_by_opening: Counter = Counter()
    wdl_counts: Counter = Counter()
    winner_counts: Counter = Counter()
    phase_counts: Counter = Counter()
    stratum_counts: Counter = Counter()
    source_counts: Counter = Counter()
    conversion_total: Counter = Counter()
    conversion_wins: Counter = Counter()

    for record, row in zip(records, rows):
        position = record[:33]
        unique_positions.add(position)
        records_by_game[row.game_id] += 1
        records_by_opening[row.opening_id] += 1
        source_counts["frontier" if row.seeded else "standard"] += 1

        wdl = struct.unpack_from("<b", record, 37)[0]
        wdl_counts[{1: "win", 0: "draw", -1: "loss"}[wdl]] += 1
        winner = _winner(record)
        winner_counts[winner if winner is not None else "draw"] += 1

        advantaged, margin, pieces = _material(record)
        phase_counts[_phase_band(pieces)] += 1
        stratum = _material_stratum(margin)
        stratum_counts[stratum] += 1
        unique_by_stratum[stratum].add(position)
        if advantaged is not None:
            conversion_total[stratum] += 1
            if winner == advantaged:
                conversion_wins[stratum] += 1

    conversion = {}
    for stratum in ("p1_clear", "p2_medium", "p3_thin"):
        total = conversion_total[stratum]
        won = conversion_wins[stratum]
        conversion[stratum] = {
            "records": total,
            "converted_records": won,
            "rate": won / total if total else None,
        }

    data_path = Path(args.data)
    meta_path = Path(args.meta)
    total_records = len(records)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "profile_selfplay",
        "diagnostic_only": True,
        "input": {
            "data": str(data_path),
            "meta": str(meta_path),
            "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "meta_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
        },
        "records": total_records,
        "games": len(records_by_game),
        "openings": len(records_by_opening),
        "unique_positions": len(unique_positions),
        "duplicate_position_records": total_records - len(unique_positions),
        "unique_position_ratio": (
            len(unique_positions) / total_records if total_records else 0.0
        ),
        "records_per_game": _count_summary(records_by_game),
        "records_per_opening": _count_summary(records_by_opening),
        "wdl_stm": dict(sorted(wdl_counts.items())),
        "terminal_winner": dict(sorted(winner_counts.items())),
        "phase_records": dict(sorted(phase_counts.items())),
        "material_stratum_records": dict(sorted(stratum_counts.items())),
        "material_stratum_unique_positions": {
            key: len(value) for key, value in sorted(unique_by_stratum.items())
        },
        "record_level_conversion": conversion,
        "record_level_conversion_unit": "correlated_position_record_not_gate",
        "source_records": dict(sorted(source_counts.items())),
    })
    return 0


def _zero_targets(record: bytes) -> bytes:
    return record[:33] + struct.pack("<i", 0) + struct.pack("<b", 0)


def _rot50(value: int) -> int:
    result = 0
    while value:
        lsb = value & -value
        square = lsb.bit_length() - 1
        result |= 1 << (49 - square)
        value ^= lsb
    return result


def mirror_record(record: bytes) -> bytes:
    """Rotate 180 degrees, swap colours and flip side-to-move."""
    return _mirror_position(record) + struct.pack("<i", 0) + struct.pack("<b", 0)


def _mirror_position(record: bytes) -> bytes:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    return struct.pack(
        "<QQQQB", _rot50(bm), _rot50(bk), _rot50(wm), _rot50(wk), 1 - stm
    )


def _mirror_record_preserve_targets(record: bytes) -> bytes:
    """Mirror a replay record while preserving its STM-POV score and WDL."""
    return _mirror_position(record) + record[33:]


def _canonical_position(record: bytes) -> bytes:
    position = record[:33]
    return min(position, _mirror_position(record))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split_manifest(split_path: Path, total: int) -> tuple[dict, int]:
    try:
        split = json.loads(split_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{split_path}: unreadable split manifest") from exc
    required = {
        "schema": 1,
        "operation": "split",
        "split_unit": "opening_id",
        "tail_is_holdout": True,
    }
    for key, expected in required.items():
        if split.get(key) != expected:
            raise ValueError(
                f"{split_path}: incompatible {key}: "
                f"{split.get(key)!r} != {expected!r}"
            )
    train_count = split.get("train_records")
    holdout_count = split.get("holdout_records")
    if (
        not isinstance(train_count, int)
        or not isinstance(holdout_count, int)
        or train_count < 0
        or holdout_count < 0
        or train_count + holdout_count != total
        or split.get("records") != total
    ):
        raise ValueError(f"{split_path}: split record counts do not match inputs")
    return split, train_count


def _split_opening_sets(
    split_path: Path, meta_path: Path, total: int, train_count: int
) -> tuple[set[int], set[int]]:
    """Validate train/holdout opening isolation with bounded memory."""
    meta_schema, meta_count = _meta_file_info(meta_path)
    if meta_count != total:
        raise ValueError("data/meta count mismatch")
    train_openings: set[int] = set()
    holdout_openings: set[int] = set()
    with meta_path.open("rb") as stream:
        stream.seek(8)
        for index in range(total):
            raw = stream.read(meta_schema.record.size)
            if len(raw) != meta_schema.record.size:
                raise ValueError(f"metadata truncated at record {index}")
            row = _decode_meta(
                raw, meta_schema, context=f"{meta_path}: record {index}"
            )
            target = train_openings if index < train_count else holdout_openings
            target.add(row.opening_id)
    overlap = train_openings & holdout_openings
    if overlap:
        raise ValueError(
            f"{split_path}: {len(overlap)} opening IDs leak across train/holdout"
        )
    return train_openings, holdout_openings


def _load_split_contract(
    split_path: Path, records: list[bytes], rows: list[Meta]
) -> tuple[dict, int]:
    split, train_count = _load_split_manifest(split_path, len(records))
    train_openings = {row.opening_id for row in rows[:train_count]}
    holdout_openings = {row.opening_id for row in rows[train_count:]}
    overlap = train_openings & holdout_openings
    if overlap:
        raise ValueError(
            f"{split_path}: {len(overlap)} opening IDs leak across train/holdout"
        )
    if (
        split.get("train_openings") != len(train_openings)
        or split.get("holdout_openings") != len(holdout_openings)
    ):
        raise ValueError(f"{split_path}: split opening counts do not match inputs")
    return split, train_count


def _hard_category(candidate: Candidate) -> tuple[str, int, int]:
    return _phase_band(candidate.pieces), candidate.margin, candidate.pieces


def _category_name(category: tuple[str, int, int]) -> str:
    phase, margin, pieces = category
    return f"{phase}|margin={margin}|pieces={pieces}"


def _hard_round_robin(
    candidates: list[Candidate], limit: int, seed: int
) -> list[Candidate]:
    buckets: dict[tuple[str, int, int], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        buckets[_hard_category(candidate)].append(candidate)
    for values in buckets.values():
        values.sort(key=lambda row: _candidate_hash(row, seed))
    selected: list[Candidate] = []
    ordered_keys = sorted(buckets)
    offset = 0
    while len(selected) < limit:
        progressed = False
        for key in ordered_keys:
            values = buckets[key]
            if offset < len(values):
                selected.append(values[offset])
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
        offset += 1
    return selected


def _wdl_label(record: bytes) -> str:
    wdl = struct.unpack_from("<b", record, 37)[0]
    return {-1: "loss", 0: "draw", 1: "win"}[wdl]


def _distribution(candidates: list[Candidate]) -> dict:
    return {
        "phase": dict(
            sorted(Counter(_phase_band(row.pieces) for row in candidates).items())
        ),
        "material_margin": {
            str(key): value
            for key, value in sorted(
                Counter(row.margin for row in candidates).items()
            )
        },
        "piece_count": {
            str(key): value
            for key, value in sorted(
                Counter(row.pieces for row in candidates).items()
            )
        },
        "wdl_stm": dict(
            sorted(Counter(_wdl_label(row.record) for row in candidates).items())
        ),
    }


def do_mine_hard(args: argparse.Namespace) -> int:
    if args.signal != "failed_conversion":
        raise ValueError("--signal must be failed_conversion for hard-mining v1")
    if not args.one_per_game:
        raise ValueError("--one-per-game is mandatory for hard-mining v1")
    if not args.colour_mirror:
        raise ValueError("--colour-mirror is mandatory for hard-mining v1")
    if args.max_records < 2 or args.max_records % 2:
        raise ValueError("--max-records must be an even integer >= 2")
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_sha):
        raise ValueError("--code-sha must be a full lowercase 40-hex commit SHA")

    paths = {
        "data": Path(args.data),
        "meta": Path(args.meta),
        "split_manifest": Path(args.split_manifest),
        "hard_replay": Path(args.out_replay),
        "hard_replay_meta": Path(args.out_meta),
        "hard_seeds": Path(args.out_seeds),
        "manifest": Path(args.manifest),
    }
    resolved = [path.resolve() for path in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("all input and output paths must be distinct")
    for name in ("hard_replay", "hard_replay_meta", "hard_seeds", "manifest"):
        if paths[name].exists():
            raise ValueError(f"refusing to overwrite existing output: {paths[name]}")

    total = _counted_file_count(paths["data"], JNNW_MAGIC, JNNW_REC)
    input_meta_schema, meta_count = _meta_file_info(paths["meta"])
    if meta_count != total:
        raise ValueError("data/meta count mismatch")
    if input_meta_schema is JSM2_SCHEMA:
        raise ValueError(
            "mine-hard does not accept JSM2: colour-mirrored replay records "
            "do not belong to the original played trajectory"
        )
    split, train_count = _load_split_manifest(paths["split_manifest"], total)
    train_openings, holdout_openings = _split_opening_sets(
        paths["split_manifest"], paths["meta"], total, train_count
    )
    if (
        split.get("train_openings") != len(train_openings)
        or split.get("holdout_openings") != len(holdout_openings)
    ):
        raise ValueError(
            f"{paths['split_manifest']}: split opening counts do not match inputs"
        )
    holdout_count = total - train_count
    if train_count == 0 or holdout_count == 0:
        raise ValueError("hard-mining requires non-empty train and holdout partitions")

    # Keep at most one candidate per game while scanning.  On the 40M source
    # this avoids retaining millions of correlated failed-conversion records.
    signal_records = 0
    candidate_categories: Counter = Counter()
    by_game: dict[int, Candidate] = {}
    for index, record, row in iter_pair(paths["data"], paths["meta"]):
        if index >= train_count:
            break
        stm = record[32]
        wdl = struct.unpack_from("<b", record, 37)[0]
        if stm not in (0, 1):
            raise ValueError(f"train record {index}: invalid side-to-move {stm}")
        if wdl not in (-1, 0, 1):
            raise ValueError(f"train record {index}: invalid WDL {wdl}")
        if row.seeded not in (0, 1):
            raise ValueError(f"train meta record {index}: invalid seeded flag")
        advantaged, margin, pieces = _material(record)
        if advantaged is None or _winner(record) == advantaged:
            continue
        candidate = Candidate(
            record, row, "failed_conversion", margin, pieces
        )
        signal_records += 1
        candidate_categories[
            _category_name(_hard_category(candidate))
        ] += 1
        previous = by_game.get(candidate.meta.game_id)
        if previous is None or _candidate_hash(
            candidate, args.seed
        ) < _candidate_hash(previous, args.seed):
            by_game[candidate.meta.game_id] = candidate
    one_per_game = list(by_game.values())

    by_position: dict[bytes, Candidate] = {}
    for candidate in one_per_game:
        key = _canonical_position(candidate.record)
        previous = by_position.get(key)
        if previous is None or _candidate_hash(
            candidate, args.seed
        ) < _candidate_hash(previous, args.seed):
            by_position[key] = candidate
    eligible = list(by_position.values())

    base_limit = args.max_records // 2
    selected = _hard_round_robin(eligible, base_limit, args.seed)
    if not selected:
        raise ValueError("no failed-conversion candidate found in train partition")

    replay_records: list[bytes] = []
    replay_meta: list[Meta] = []
    for candidate in selected:
        replay_records.extend(
            (candidate.record, _mirror_record_preserve_targets(candidate.record))
        )
        replay_meta.extend((candidate.meta, candidate.meta))
    seed_records = [_zero_targets(record) for record in replay_records]

    selected_openings = {row.opening_id for row in replay_meta}
    leaked_openings = selected_openings & holdout_openings
    if leaked_openings:
        raise ValueError(
            f"selected output leaks {len(leaked_openings)} holdout openings"
        )
    if len({_canonical_position(record) for record in replay_records}) != len(
        selected
    ):
        raise ValueError("internal error: colour-canonical output dedup failed")

    _write_pair_atomic(
        paths["hard_replay"],
        paths["hard_replay_meta"],
        replay_records,
        replay_meta,
    )
    seed_payload = (
        JNNW_MAGIC
        + struct.pack("<I", len(seed_records))
        + b"".join(seed_records)
    )
    _atomic_write_bytes(paths["hard_seeds"], seed_payload)

    # Read every output back before publishing the manifest, which is the
    # completion marker for consumers.
    checked_replay, checked_meta = read_pair(
        paths["hard_replay"], paths["hard_replay_meta"]
    )
    seed_count, seed_body = _read_counted(
        paths["hard_seeds"], JNNW_MAGIC, JNNW_REC
    )
    checked_seeds = [
        seed_body[index * JNNW_REC:(index + 1) * JNNW_REC]
        for index in range(seed_count)
    ]
    if checked_replay != replay_records or checked_meta != replay_meta:
        raise ValueError("hard replay read-back verification failed")
    if checked_seeds != seed_records:
        raise ValueError("hard seed read-back verification failed")
    if any(record[33:] != source[33:] for record, source in zip(
        checked_replay, replay_records
    )):
        raise ValueError("hard replay targets were not preserved")
    if any(record[33:] != b"\0\0\0\0\0" for record in checked_seeds):
        raise ValueError("hard seed targets were not zeroed")

    eligible_categories = Counter(
        _category_name(_hard_category(row)) for row in eligible
    )
    selected_categories = Counter(
        _category_name(_hard_category(row)) for row in selected
    )
    payload = {
        "schema": 1,
        "operation": "mine-hard",
        "signal": "failed_conversion",
        "signal_definition": (
            "material advantage observed; terminal outcome non-winning "
            "for advantaged side"
        ),
        "code_sha": args.code_sha,
        "seed": args.seed,
        "max_records_including_colour_mirrors": args.max_records,
        "one_per_game": True,
        "colour_mirror": True,
        "selection_scope": "train_only",
        "holdout_records_examined_for_signal": 0,
        "quota_policy": (
            "deterministic round-robin over "
            "(phase, exact material margin, exact piece count)"
        ),
        "external_teacher_inputs": 0,
        "input": {
            "data": str(paths["data"]),
            "data_sha256": _sha256(paths["data"]),
            "meta": str(paths["meta"]),
            "meta_sha256": _sha256(paths["meta"]),
            "split_manifest": str(paths["split_manifest"]),
            "split_manifest_sha256": _sha256(paths["split_manifest"]),
            "records": total,
        },
        "split": {
            "schema": split["schema"],
            "split_unit": split["split_unit"],
            "seed": split.get("seed"),
            "holdout_mod": split.get("holdout_mod"),
            "train_records": train_count,
            "holdout_records": holdout_count,
            "tail_is_holdout": True,
            "verified_opening_disjoint": True,
            "selected_holdout_opening_overlap": 0,
        },
        "candidates": {
            "signal_records": signal_records,
            "games": len(by_game),
            "after_one_per_game": len(one_per_game),
            "after_canonical_dedup": len(eligible),
            "by_category": dict(sorted(candidate_categories.items())),
            "eligible_by_category": dict(sorted(eligible_categories.items())),
        },
        "selection": {
            "base_positions": len(selected),
            "output_records": len(replay_records),
            "unique_games": len({row.meta.game_id for row in selected}),
            "unique_openings": len({row.meta.opening_id for row in selected}),
            "unique_canonical_positions": len(
                {_canonical_position(row.record) for row in selected}
            ),
            "by_category": dict(sorted(selected_categories.items())),
            "distribution": _distribution(selected),
        },
        "deduplication": {
            "one_per_game_dropped": signal_records - len(one_per_game),
            "canonical_position_dropped": len(one_per_game) - len(eligible),
        },
        "targets": {
            "hard_replay_original_wdl_and_score_preserved": True,
            "hard_seeds_score_zero": all(
                struct.unpack_from("<i", record, 33)[0] == 0
                for record in checked_seeds
            ),
            "hard_seeds_wdl_zero": all(
                struct.unpack_from("<b", record, 37)[0] == 0
                for record in checked_seeds
            ),
            "hard_seeds_zero_target_records": len(checked_seeds),
        },
        "outputs": {
            "hard_replay": {
                "path": str(paths["hard_replay"]),
                "sha256": _sha256(paths["hard_replay"]),
                "records": len(checked_replay),
            },
            "hard_replay_meta": {
                "path": str(paths["hard_replay_meta"]),
                "sha256": _sha256(paths["hard_replay_meta"]),
                "records": len(checked_meta),
            },
            "hard_seeds": {
                "path": str(paths["hard_seeds"]),
                "sha256": _sha256(paths["hard_seeds"]),
                "records": len(checked_seeds),
            },
        },
    }
    _atomic_write_text(
        paths["manifest"],
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return 0


def _round_robin(candidates: list[Candidate], limit: int, seed: int) -> list[Candidate]:
    buckets: dict[tuple[str, int, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        buckets[(candidate.kind, candidate.margin, _piece_band(candidate.pieces))].append(candidate)
    for values in buckets.values():
        values.sort(key=lambda row: _candidate_hash(row, seed))
    ordered_keys = sorted(buckets)
    selected: list[Candidate] = []
    offset = 0
    while len(selected) < limit:
        progressed = False
        for key in ordered_keys:
            values = buckets[key]
            if offset < len(values):
                selected.append(values[offset])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        offset += 1
    return selected


def do_mine(args: argparse.Namespace) -> int:
    if args.max_positions < 2:
        raise ValueError("--max-positions must be >= 2")
    if not 0.0 <= args.converted_fraction <= 1.0:
        raise ValueError("--converted-fraction must be in [0,1]")
    records, rows = read_pair(Path(args.data), Path(args.meta))
    best: dict[tuple[int, str], Candidate] = {}
    observed: Counter = Counter()
    for record, row in zip(records, rows):
        advantaged, margin, pieces = _material(record)
        if advantaged is None or not args.margin_min <= margin <= args.margin_max:
            continue
        if not args.min_pieces <= pieces <= args.max_pieces:
            continue
        kind = "converted" if _winner(record) == advantaged else "failed_conversion"
        candidate = Candidate(record, row, kind, margin, pieces)
        observed[kind] += 1
        key = (row.game_id, kind)
        previous = best.get(key)
        if previous is None or _candidate_hash(candidate, args.seed) < _candidate_hash(previous, args.seed):
            best[key] = candidate

    unique = list(best.values())
    failed = [row for row in unique if row.kind == "failed_conversion"]
    converted = [row for row in unique if row.kind == "converted"]
    # Output is colour-paired, so select at most half the requested base records.
    base_limit = args.max_positions // 2
    converted_limit = round(base_limit * args.converted_fraction)
    failed_limit = base_limit - converted_limit
    selected = _round_robin(failed, failed_limit, args.seed)
    selected += _round_robin(converted, converted_limit, args.seed ^ 0xA5A5A5A5)
    if len(selected) < base_limit:
        chosen = {(row.meta.game_id, row.kind) for row in selected}
        remainder = [row for row in failed + converted
                     if (row.meta.game_id, row.kind) not in chosen]
        selected += _round_robin(remainder, base_limit - len(selected), args.seed ^ 0x5A5A5A5A)

    output_records: list[bytes] = []
    seen_positions: set[bytes] = set()
    selected_counts: Counter = Counter()
    for candidate in selected:
        original = _zero_targets(candidate.record)
        for paired in (original, mirror_record(original)):
            key = paired[:33]
            if key in seen_positions or len(output_records) >= args.max_positions:
                continue
            seen_positions.add(key)
            output_records.append(paired)
        selected_counts[candidate.kind] += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(JNNW_MAGIC + struct.pack("<I", len(output_records)) + b"".join(output_records))
    digest = hashlib.sha256(Path(args.data).read_bytes()).hexdigest()
    margin_counts = Counter(row.margin for row in selected)
    piece_counts = Counter(_piece_band(row.pieces) for row in selected)
    source_counts = Counter("frontier" if row.meta.seeded else "standard" for row in selected)
    _manifest(args.manifest, {
        "schema": 1,
        "operation": "mine_frontier",
        "input_sha256": digest,
        "input_records": len(records),
        "candidate_records": dict(sorted(observed.items())),
        "candidate_games": len(unique),
        "selected_base_positions": len(selected),
        "output_positions_with_colour_mirrors": len(output_records),
        "selected_kind": dict(sorted(selected_counts.items())),
        "selected_margin": {str(k): v for k, v in sorted(margin_counts.items())},
        "selected_piece_band": dict(sorted(piece_counts.items())),
        "selected_source": dict(sorted(source_counts.items())),
        "labels_used_for_selection_only": True,
        "output_score_and_wdl_zeroed": True,
        "external_teacher_inputs": 0,
    })
    return 0 if output_records else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    merge = sub.add_parser("merge", help="merge aligned JNNW/JSM1-or-JSM2 shards")
    merge.add_argument("--pair", nargs=2, action="append", required=True,
                       metavar=("DATA", "META"))
    merge.add_argument("--out-data", required=True)
    merge.add_argument("--out-meta", required=True)
    merge.add_argument("--manifest")
    merge.add_argument(
        "--renamespace-nested",
        action="store_true",
        help="remap existing 64-bit game/opening IDs per input while preserving equality groups",
    )
    merge.add_argument("--wdl-min-draw-share", type=float, default=None,
                       help="plancher de nulles du corpus fusionné (défaut 0,10). "
                            "À abaisser EXPLICITEMENT pour une lignée dont "
                            "l'asymétrie est voulue (IMBALANCE2 part d'un "
                            "avantage matériel, ses nulles sont rares par "
                            "construction)")
    merge.add_argument("--wdl-max-draw-share", type=float, default=None,
                       help="plafond de nulles (défaut 0,60)")
    merge.add_argument("--wdl-max-side-skew", type=float, default=None,
                       help="écart max victoires/défaites (défaut 0,10)")
    merge.add_argument("--no-wdl-check", action="store_true",
                       help="désactive le canari. Réservé à l'archéologie sur "
                            "un corpus historique déjà connu comme défectueux")
    merge.set_defaults(func=do_merge)

    mix = sub.add_parser("mix", help="build an exact weighted aligned JNNW/JSM1-or-JSM2 mix")
    mix.add_argument(
        "--source",
        nargs=4,
        action="append",
        required=True,
        metavar=("LABEL", "DATA", "META", "WEIGHT"),
    )
    mix.add_argument("--target-records", type=int, required=True)
    mix.add_argument("--seed", type=int, required=True)
    mix.add_argument("--out-data", required=True)
    mix.add_argument("--out-meta", required=True)
    mix.add_argument("--manifest")
    mix.add_argument(
        "--namespace-openings",
        action="store_true",
        help=(
            "namespace opening IDs by source when corpora do not share paired "
            "opening identities"
        ),
    )
    mix.set_defaults(func=do_mix)

    split = sub.add_parser("split", help="make an opening-level holdout tail")
    split.add_argument("--data", required=True)
    split.add_argument("--meta", required=True)
    split.add_argument("--out-data", required=True)
    split.add_argument("--out-meta", required=True)
    split.add_argument("--holdout-mod", type=int, default=10)
    split.add_argument("--seed", type=int, default=1)
    split.add_argument("--manifest")
    split.set_defaults(func=do_split)

    mine = sub.add_parser("mine", help="mine a moving, self-generated conversion frontier")
    mine.add_argument("--data", required=True)
    mine.add_argument("--meta", required=True)
    mine.add_argument("--out", required=True)
    mine.add_argument("--manifest")
    mine.add_argument("--max-positions", type=int, default=4000,
                      help="total output count including colour mirrors")
    mine.add_argument("--min-pieces", type=int, default=8)
    mine.add_argument("--max-pieces", type=int, default=24)
    mine.add_argument("--margin-min", type=int, default=1)
    mine.add_argument("--margin-max", type=int, default=3)
    mine.add_argument("--converted-fraction", type=float, default=0.20,
                      help="calibration share of successfully converted positions")
    mine.add_argument("--seed", type=int, default=1)
    mine.set_defaults(func=do_mine)

    hard = sub.add_parser(
        "mine-hard",
        help="mine train-only failed conversions into replay and zero-target seeds",
    )
    hard.add_argument("--data", required=True)
    hard.add_argument("--meta", required=True)
    hard.add_argument("--split-manifest", required=True)
    hard.add_argument("--out-replay", required=True)
    hard.add_argument("--out-meta", required=True)
    hard.add_argument("--out-seeds", required=True)
    hard.add_argument("--manifest", required=True)
    hard.add_argument("--max-records", type=int, required=True,
                      help="maximum total output count including colour mirrors")
    hard.add_argument("--seed", type=int, required=True)
    hard.add_argument("--signal", choices=("failed_conversion",), required=True)
    hard.add_argument("--one-per-game", action="store_true")
    hard.add_argument("--colour-mirror", action="store_true")
    hard.add_argument("--code-sha", required=True)
    hard.set_defaults(func=do_mine_hard)

    profile = sub.add_parser("profile", help="profile self-play coverage and diversity")
    profile.add_argument("--data", required=True)
    profile.add_argument("--meta", required=True)
    profile.add_argument("--manifest", required=True)
    profile.set_defaults(func=do_profile)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
