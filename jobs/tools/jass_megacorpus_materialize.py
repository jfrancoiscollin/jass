#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Materialize an authenticated, game-aware Jass MegaCorpus smoke corpus.

The input JSON explicitly names immutable source pairs and their expected raw
hashes.  Selection happens at complete-game granularity.  Selected rows are
written train-first/holdout-last by opening, while compact NumPy sidecars keep
the source id and original source-row index of every output example.

The merged metadata is deliberately JSM1.  Original JSM1/JSM2 files remain
immutable at their source URI and are authenticated in ``source-table.json``;
the tool never invents the JSM2 fields that older sources did not contain.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Iterator

import numpy as np


JNNW_DTYPE = np.dtype(
    [
        ("wm", "<u8"),
        ("wk", "<u8"),
        ("bm", "<u8"),
        ("bk", "<u8"),
        ("stm", "u1"),
        ("score", "<i4"),
        ("wdl", "i1"),
    ]
)
JSM1_DTYPE = np.dtype(
    [("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1")]
)
JSM2_DTYPE = np.dtype(
    [
        ("game_id", "<u8"),
        ("opening_id", "<u8"),
        ("seeded", "u1"),
        ("ply", "<u2"),
        ("game_plies", "<u2"),
        ("last_eps_ply", "<u2"),
        ("game_result", "i1"),
        ("flags", "u1"),
    ]
)
assert JNNW_DTYPE.itemsize == 38
assert JSM1_DTYPE.itemsize == 17
assert JSM2_DTYPE.itemsize == 25


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_counted(path: Path, expected_magic: bytes, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != expected_magic:
        raise ValueError(f"{path}: expected {expected_magic!r} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected_size = 8 + count * dtype.itemsize
    if path.stat().st_size != expected_size:
        raise ValueError(f"{path}: size {path.stat().st_size} != {expected_size}")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(count,))


def open_meta(path: Path, expected_count: int) -> tuple[np.memmap, str]:
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic == b"JSM1":
        rows = open_counted(path, magic, JSM1_DTYPE)
    elif magic == b"JSM2":
        rows = open_counted(path, magic, JSM2_DTYPE)
    else:
        raise ValueError(f"{path}: expected JSM1 or JSM2 header")
    if len(rows) != expected_count:
        raise ValueError(f"{path}: metadata rows {len(rows)} != data {expected_count}")
    return rows, magic.decode("ascii")


def splitmix64(value: int) -> int:
    mask = (1 << 64) - 1
    value = (value + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return (value ^ (value >> 31)) & mask


def keyed_hash(source_id: int, value: int, seed: int) -> int:
    mixed_source = splitmix64(source_id ^ seed ^ 0xA0761D6478BD642F)
    return splitmix64((value ^ mixed_source) & ((1 << 64) - 1))


def iter_game_ranges(game_ids: np.ndarray, chunk_rows: int) -> Iterator[tuple[int, int]]:
    """Yield contiguous [start, end) game ranges without a full-size index."""
    count = len(game_ids)
    if count == 0:
        return
    game_start = 0
    previous = int(game_ids[0])
    position = 1
    while position < count:
        end = min(count, position + chunk_rows)
        chunk = np.asarray(game_ids[position:end], dtype=np.uint64)
        prior = np.empty(len(chunk), dtype=np.uint64)
        prior[0] = previous
        if len(chunk) > 1:
            prior[1:] = chunk[:-1]
        changes = np.flatnonzero(chunk != prior)
        for local in changes:
            boundary = position + int(local)
            yield game_start, boundary
            game_start = boundary
        previous = int(chunk[-1])
        position = end
    yield game_start, count


def validate_data(rows: np.ndarray, *, chunk_rows: int) -> dict[str, Any]:
    wdl = Counter()
    stm = Counter()
    for start in range(0, len(rows), chunk_rows):
        chunk = rows[start:start + chunk_rows]
        overlap = (
            (chunk["wm"] & chunk["wk"])
            | (chunk["wm"] & chunk["bm"])
            | (chunk["wm"] & chunk["bk"])
            | (chunk["wk"] & chunk["bm"])
            | (chunk["wk"] & chunk["bk"])
            | (chunk["bm"] & chunk["bk"])
        )
        if np.any(overlap):
            raise ValueError(f"bitboard overlap at/after row {start}")
        values, counts = np.unique(chunk["wdl"], return_counts=True)
        wdl.update({int(value): int(count) for value, count in zip(values, counts)})
        values, counts = np.unique(chunk["stm"], return_counts=True)
        stm.update({int(value): int(count) for value, count in zip(values, counts)})
    if set(wdl) - {-1, 0, 1}:
        raise ValueError(f"WDL outside -1/0/1: {sorted(wdl)}")
    if set(stm) - {0, 1}:
        raise ValueError(f"STM outside 0/1: {sorted(stm)}")
    return {"wdl": {str(k): v for k, v in sorted(wdl.items())},
            "stm": {str(k): v for k, v in sorted(stm.items())}}


def sampling_accepts(spec: dict[str, Any], source_id: int, game_id: int) -> bool:
    sampling = spec.get("sampling") or {"mode": "all"}
    mode = sampling.get("mode", "all")
    if mode == "all":
        return True
    if mode != "game_hash_mod":
        raise ValueError(f"unsupported sampling mode: {mode!r}")
    modulus = int(sampling.get("modulus", 0))
    residue = int(sampling.get("residue", 0))
    seed = int(sampling.get("seed", 0))
    if modulus < 2 or not 0 <= residue < modulus:
        raise ValueError("game_hash_mod requires modulus >=2 and valid residue")
    return keyed_hash(source_id, game_id, seed) % modulus == residue


def write_header(handle, magic: bytes, count: int) -> None:
    if not 0 <= count < (1 << 32):
        raise ValueError(f"record count cannot be represented in counted format: {count}")
    handle.write(magic + struct.pack("<I", count))


def materialize(
    source_spec_path: Path,
    out_data: Path,
    out_meta: Path,
    origin_source_out: Path,
    origin_index_out: Path,
    source_table_out: Path,
    manifest_out: Path,
    *,
    holdout_mod: int,
    split_seed: int,
    chunk_rows: int,
) -> dict[str, Any]:
    if holdout_mod < 2:
        raise ValueError("holdout_mod must be >= 2")
    document = json.loads(source_spec_path.read_text(encoding="utf-8"))
    if document.get("schema") != "jass.megacorpus.source_selection.v1":
        raise ValueError("unexpected source selection schema")
    specs = document.get("sources")
    if not isinstance(specs, list) or not specs:
        raise ValueError("source selection must contain a non-empty sources list")
    source_ids = [int(spec["source_id"]) for spec in specs]
    if len(set(source_ids)) != len(source_ids) or min(source_ids) < 0:
        raise ValueError("source_id values must be unique non-negative integers")
    if max(source_ids) >= (1 << 32):
        raise ValueError("source_id does not fit uint32 provenance")

    loaded: list[dict[str, Any]] = []
    raw_data_hashes: set[str] = set()
    selected_total = train_total = holdout_total = 0
    selected_games = 0
    selected_intervals: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    for spec in specs:
        source_id = int(spec["source_id"])
        data_path = Path(spec["data_path"])
        meta_path = Path(spec["meta_path"])
        data_hash = sha256(data_path)
        meta_hash = sha256(meta_path)
        expected_data = spec.get("expected_data_raw_sha256")
        expected_meta = spec.get("expected_meta_raw_sha256")
        if not isinstance(expected_data, str) or len(expected_data) != 64:
            raise ValueError(f"source {source_id}: missing expected raw data SHA")
        if not isinstance(expected_meta, str) or len(expected_meta) != 64:
            raise ValueError(f"source {source_id}: missing expected raw metadata SHA")
        if data_hash != expected_data:
            raise ValueError(f"source {source_id}: data SHA drift")
        if meta_hash != expected_meta:
            raise ValueError(f"source {source_id}: metadata SHA drift")
        if data_hash in raw_data_hashes:
            raise ValueError(f"source {source_id}: exact duplicate data blob")
        raw_data_hashes.add(data_hash)
        data = open_counted(data_path, b"JNNW", JNNW_DTYPE)
        meta, meta_schema = open_meta(meta_path, len(data))
        expected_records = spec.get("expected_records")
        if expected_records is not None and len(data) != int(expected_records):
            raise ValueError(f"source {source_id}: records {len(data)} != {expected_records}")
        validation = validate_data(data, chunk_rows=chunk_rows)
        if np.any((meta["seeded"] != 0) & (meta["seeded"] != 1)):
            raise ValueError(f"source {source_id}: seeded outside 0/1")

        source_selected = source_train = source_holdout = source_games = 0
        seen_game_ids: set[int] = set()
        for start, end in iter_game_ranges(meta["game_id"], chunk_rows):
            game_id = int(meta["game_id"][start])
            opening_id = int(meta["opening_id"][start])
            if game_id in seen_game_ids:
                raise ValueError(f"source {source_id}: game {game_id} is non-contiguous")
            seen_game_ids.add(game_id)
            if np.any(meta["game_id"][start:end] != game_id):
                raise AssertionError("game range construction drift")
            if np.any(meta["opening_id"][start:end] != opening_id):
                raise ValueError(f"source {source_id}: game {game_id} changes opening id")
            if not sampling_accepts(spec, source_id, game_id):
                continue
            partition = (
                "holdout"
                if keyed_hash(source_id, opening_id, split_seed) % holdout_mod == 0
                else "train"
            )
            count = end - start
            selected_intervals.append(
                {
                    "source_index": len(loaded),
                    "source_id": source_id,
                    "start": start,
                    "end": end,
                    "game_id": game_id,
                    "opening_id": opening_id,
                    "partition": partition,
                }
            )
            source_selected += count
            source_games += 1
            if partition == "train":
                source_train += count
            else:
                source_holdout += count
        if source_selected == 0 or source_train == 0 or source_holdout == 0:
            raise ValueError(f"source {source_id}: empty selected/train/holdout cohort")

        loaded.append({"spec": spec, "data": data, "meta": meta})
        selected_total += source_selected
        train_total += source_train
        holdout_total += source_holdout
        selected_games += source_games
        source_rows.append(
            {
                "source_id": source_id,
                "name": spec.get("name"),
                "source_uri": spec.get("source_uri"),
                "source_job": spec.get("source_job"),
                "source_attempt": spec.get("source_attempt"),
                "source_code_sha": spec.get("source_code_sha"),
                "generation_date": spec.get("generation_date"),
                "generator_model": spec.get("generator_model"),
                "selfplay": spec.get("selfplay"),
                "quality_class": spec.get("quality_class"),
                "sampling": spec.get("sampling") or {"mode": "all"},
                "input_records": int(len(data)),
                "selected_records": source_selected,
                "selected_games": source_games,
                "train_records": source_train,
                "holdout_records": source_holdout,
                "data_raw_sha256": data_hash,
                "meta_raw_sha256": meta_hash,
                "meta_schema": meta_schema,
                "merged_meta_schema": "JSM1",
                "original_metadata_preserved_at_source": True,
                "validation": validation,
            }
        )

    if selected_total != train_total + holdout_total:
        raise AssertionError("partition accounting drift")

    for path in (
        out_data, out_meta, origin_source_out, origin_index_out,
        source_table_out, manifest_out,
    ):
        if path.exists():
            raise ValueError(f"{path}: output exists (no-clobber)")
        path.parent.mkdir(parents=True, exist_ok=True)
    source_mm = np.lib.format.open_memmap(
        origin_source_out, mode="w+", dtype=np.uint32, shape=(selected_total,)
    )
    index_mm = np.lib.format.open_memmap(
        origin_index_out, mode="w+", dtype=np.uint64, shape=(selected_total,)
    )
    game_fingerprints: dict[str, list[tuple[int, int]]] = defaultdict(list)
    opening_namespaces: list[dict[int, int]] = [dict() for _ in loaded]
    next_opening = 0
    next_game = 0
    cursor = 0

    with out_data.open("wb") as data_out, out_meta.open("wb") as meta_out:
        write_header(data_out, b"JNNW", selected_total)
        write_header(meta_out, b"JSM1", selected_total)
        for partition in ("train", "holdout"):
            for interval in selected_intervals:
                if interval["partition"] != partition:
                    continue
                loaded_source = loaded[interval["source_index"]]
                data = loaded_source["data"]
                meta = loaded_source["meta"]
                start, end = interval["start"], interval["end"]
                count = end - start
                opening_map = opening_namespaces[interval["source_index"]]
                original_opening = interval["opening_id"]
                if original_opening not in opening_map:
                    opening_map[original_opening] = next_opening
                    next_opening += 1
                output_opening = opening_map[original_opening]
                output_game = next_game
                next_game += 1

                data_bytes = np.asarray(data[start:end]).tobytes(order="C")
                data_out.write(data_bytes)
                merged_meta = np.empty(count, dtype=JSM1_DTYPE)
                merged_meta["game_id"] = output_game
                merged_meta["opening_id"] = output_opening
                merged_meta["seeded"] = meta["seeded"][start:end]
                meta_out.write(merged_meta.tobytes(order="C"))
                source_mm[cursor:cursor + count] = interval["source_id"]
                index_mm[cursor:cursor + count] = np.arange(start, end, dtype=np.uint64)
                fingerprint = hashlib.sha256(data_bytes).hexdigest()
                game_fingerprints[fingerprint].append((interval["source_id"], start))
                cursor += count
    source_mm.flush()
    index_mm.flush()
    del source_mm, index_mm
    if cursor != selected_total or next_game != selected_games:
        raise AssertionError("output accounting drift")

    duplicate_groups = [rows for rows in game_fingerprints.values() if len(rows) > 1]
    cross_source_groups = [
        rows for rows in duplicate_groups if len({source_id for source_id, _ in rows}) > 1
    ]
    source_table = {
        "schema": "jass.megacorpus.source_table.v1",
        "selection_policy": document.get("selection_policy"),
        "sources": source_rows,
    }
    source_table_out.write_text(
        json.dumps(source_table, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema": "jass.megacorpus.materialization.v1",
        "records": selected_total,
        "train_records": train_total,
        "holdout_records": holdout_total,
        "games": selected_games,
        "openings": next_opening,
        "holdout_mod": holdout_mod,
        "split_seed": split_seed,
        "output_meta_schema": "JSM1",
        "train_first_holdout_last": True,
        "source_count": len(source_rows),
        "source_record_counts": {
            str(row["source_id"]): row["selected_records"] for row in source_rows
        },
        "exact_duplicate_source_blobs_removed": 0,
        "selected_game_fingerprint_duplicate_groups": len(duplicate_groups),
        "selected_cross_source_game_duplicate_groups": len(cross_source_groups),
        "files": {
            "data": {"path": str(out_data), "sha256": sha256(out_data)},
            "meta": {"path": str(out_meta), "sha256": sha256(out_meta)},
            "origin_source_id": {
                "path": str(origin_source_out), "sha256": sha256(origin_source_out),
                "dtype": "uint32", "shape": [selected_total],
            },
            "origin_record_index": {
                "path": str(origin_index_out), "sha256": sha256(origin_index_out),
                "dtype": "uint64", "shape": [selected_total],
            },
            "source_table": {
                "path": str(source_table_out), "sha256": sha256(source_table_out),
            },
        },
        "frozen_cohorts_read": 0,
        "external_teacher_inputs": 0,
        "promotion_authorized": False,
    }
    manifest_out.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-spec", required=True, type=Path)
    parser.add_argument("--out-data", required=True, type=Path)
    parser.add_argument("--out-meta", required=True, type=Path)
    parser.add_argument("--origin-source-out", required=True, type=Path)
    parser.add_argument("--origin-index-out", required=True, type=Path)
    parser.add_argument("--source-table-out", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--holdout-mod", type=int, default=10)
    parser.add_argument("--split-seed", type=int, default=577215)
    parser.add_argument("--chunk-rows", type=int, default=1_000_000)
    args = parser.parse_args(argv)
    try:
        manifest = materialize(
            args.source_spec,
            args.out_data,
            args.out_meta,
            args.origin_source_out,
            args.origin_index_out,
            args.source_table_out,
            args.manifest,
            holdout_mod=args.holdout_mod,
            split_seed=args.split_seed,
            chunk_rows=args.chunk_rows,
        )
        print(json.dumps(manifest, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"jass_megacorpus_materialize: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
