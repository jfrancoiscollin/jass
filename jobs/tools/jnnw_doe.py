#!/usr/bin/env python3
"""Utilities for matched-corpus JNNW factorial experiments.

The experiment contract is stricter than a normal data-preparation script:

* positions are identified by bitboards + side-to-move (the first 33 bytes);
* relabelled records are normalized so that only the WDL byte changes;
* relabel shards are contiguous and merged in their original order;
* all DOE cells share the same ordered unique-position prefix;
* gym weighting is represented only by deterministic repetitions of the same
  gym records, never by adding different positions to one cell.

JNNW v1 record layout (38 bytes):
    wm:u64, wk:u64, bm:u64, bk:u64, stm:u8, score:i32, wdl:i8
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

MAGIC = b"JNNW"
REC = 38
POS = 33  # 4 bitboards + side-to-move; excludes score and WDL


def _read(path: str | Path) -> tuple[int, bytes]:
    raw = Path(path).read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW header")
    n = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != n * REC:
        raise ValueError(f"{path}: header says {n} records, body has {len(body)} bytes")
    return n, body


def _write(path: str | Path, records: Iterable[bytes]) -> int:
    rows = list(records)
    if any(len(r) != REC for r in rows):
        raise ValueError("attempted to write a non-38-byte JNNW record")
    Path(path).write_bytes(MAGIC + struct.pack("<I", len(rows)) + b"".join(rows))
    return len(rows)


def _records(body: bytes) -> Iterator[bytes]:
    for off in range(0, len(body), REC):
        yield body[off:off + REC]


def _record_key(rec: bytes) -> bytes:
    return rec[:POS]


def _sha_records(records: Iterable[bytes], *, positions_only: bool = False) -> str:
    h = hashlib.sha256()
    for rec in records:
        h.update(_record_key(rec) if positions_only else rec)
    return h.hexdigest()


def _parse_fen(fen: str) -> bytes:
    """Convert an international-draughts FEN into a placeholder JNNW record."""
    try:
        stm_part, white_part, black_part = fen.strip().split(":")
    except ValueError as exc:
        raise ValueError(f"bad FEN: {fen!r}") from exc
    stm_ch = stm_part.strip().upper()
    if stm_ch not in {"W", "B"}:
        raise ValueError(f"bad side-to-move in FEN: {fen!r}")
    if not white_part.startswith("W") or not black_part.startswith("B"):
        raise ValueError(f"bad colour sections in FEN: {fen!r}")

    wm = wk = bm = bk = 0

    def add(part: str, colour: str) -> None:
        nonlocal wm, wk, bm, bk
        for token in part[1:].split(","):
            token = token.strip()
            if not token:
                continue
            king = token.startswith("K")
            square_text = token[1:] if king else token
            if not square_text.isdigit():
                raise ValueError(f"bad square {token!r} in FEN: {fen!r}")
            square = int(square_text)
            if not 1 <= square <= 50:
                raise ValueError(f"square out of range {square} in FEN: {fen!r}")
            bit = 1 << (square - 1)
            if (wm | wk | bm | bk) & bit:
                raise ValueError(f"duplicate square {square} in FEN: {fen!r}")
            if colour == "W":
                if king:
                    wk |= bit
                else:
                    wm |= bit
            else:
                if king:
                    bk |= bit
                else:
                    bm |= bit

    add(white_part, "W")
    add(black_part, "B")
    stm = 0 if stm_ch == "W" else 1
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, 0)


def _fen_rows(path: str | Path) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fen, _, comment = raw.partition("#")
        fen = fen.strip()
        if fen:
            rows.append((fen, comment.strip() or None))
    return rows


def cmd_subset_fen(args: argparse.Namespace) -> None:
    rows = _fen_rows(args.input)
    if not rows:
        raise ValueError("input FEN pool is empty")
    grouped: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    pal_re = re.compile(r"(?:^|\s)palier=([^\s]+)")
    for fen, comment in rows:
        match = pal_re.search(comment or "")
        grouped[match.group(1) if match else "unclassified"].append((fen, comment))

    if args.per_group:
        selected: list[tuple[str, str | None]] = []
        for group in sorted(grouped):
            bucket = grouped[group]
            take = min(args.per_group, len(bucket))
            if take == 0:
                continue
            idx = [math.floor(i * len(bucket) / take) for i in range(take)]
            selected.extend(bucket[i] for i in idx)
    else:
        take = min(args.count, len(rows))
        idx = [math.floor(i * len(rows) / take) for i in range(take)]
        selected = [rows[i] for i in idx]

    with Path(args.output).open("w", encoding="utf-8") as fh:
        fh.write(f"# deterministic DOE subset from {Path(args.input).name} — {len(selected)} positions\n")
        for fen, comment in selected:
            fh.write(fen)
            if comment:
                fh.write(f"  # {comment}")
            fh.write("\n")
    print(json.dumps({"selected": len(selected), "groups": {k: len(v) for k, v in grouped.items()}}))


def cmd_fen_to_jnnw(args: argparse.Namespace) -> None:
    rows = _fen_rows(args.input)
    records = [_parse_fen(fen) for fen, _ in rows]
    if len({_record_key(r) for r in records}) != len(records):
        raise ValueError("FEN pool contains duplicate positions")
    _write(args.output, records)
    print(json.dumps({"records": len(records), "position_sha256": _sha_records(records, positions_only=True)}))


def cmd_sample(args: argparse.Namespace) -> None:
    n, body = _read(args.input)
    excluded: set[bytes] = set()
    for fen_file in args.exclude_fen or []:
        excluded.update(_record_key(_parse_fen(fen)) for fen, _ in _fen_rows(fen_file))

    eligible = []
    seen: set[bytes] = set()
    duplicate_positions = 0
    for i, rec in enumerate(_records(body)):
        key = _record_key(rec)
        if key in excluded:
            continue
        if key in seen:
            duplicate_positions += 1
            continue
        seen.add(key)
        eligible.append(i)
    if len(eligible) < args.count:
        raise ValueError(f"only {len(eligible)} unique eligible records for requested sample {args.count}")
    selected_idx = [eligible[math.floor(i * len(eligible) / args.count)] for i in range(args.count)]
    records = [body[i * REC:(i + 1) * REC] for i in selected_idx]
    _write(args.output, records)
    print(json.dumps({
        "input": n,
        "eligible": len(eligible),
        "selected": len(records),
        "excluded_positions": len(excluded),
        "duplicate_positions_skipped": duplicate_positions,
        "position_sha256": _sha_records(records, positions_only=True),
    }))


def cmd_split(args: argparse.Namespace) -> None:
    if args.shards <= 0:
        raise ValueError("shards must be > 0")
    n, body = _read(args.input)
    counts = []
    start = 0
    for shard in range(args.shards):
        end = (n * (shard + 1)) // args.shards
        records = list(_records(body[start * REC:end * REC]))
        path = f"{args.prefix}.{shard:03d}.jnnw"
        _write(path, records)
        counts.append(len(records))
        start = end
    print(json.dumps({"records": n, "shards": args.shards, "counts": counts}))


def cmd_merge(args: argparse.Namespace) -> None:
    merged: list[bytes] = []
    counts = []
    for shard in range(args.shards):
        out_path = f"{args.prefix}.{shard:03d}.jnnw"
        n, body = _read(out_path)
        rows = list(_records(body))
        counts.append(n)
        merged.extend(rows)
        if args.source_prefix:
            src_path = f"{args.source_prefix}.{shard:03d}.jnnw"
            sn, sbody = _read(src_path)
            if sn != n:
                raise ValueError(f"shard {shard}: source={sn}, relabelled={n}")
            src_rows = list(_records(sbody))
            for idx, (src, out) in enumerate(zip(src_rows, rows)):
                if _record_key(src) != _record_key(out):
                    raise ValueError(f"shard {shard} record {idx}: relabel changed/reordered the position")
    if args.expected is not None and len(merged) != args.expected:
        raise ValueError(f"merged {len(merged)} records, expected {args.expected}")
    _write(args.output, merged)
    print(json.dumps({"records": len(merged), "counts": counts, "position_sha256": _sha_records(merged, positions_only=True)}))


def cmd_normalize_labels(args: argparse.Namespace) -> None:
    rn, rbody = _read(args.reference)
    ln, lbody = _read(args.relabeled)
    if rn != ln:
        raise ValueError(f"reference has {rn} records, relabelled has {ln}")
    out: list[bytes] = []
    changed = decisive = 0
    for idx, (ref, lab) in enumerate(zip(_records(rbody), _records(lbody))):
        if _record_key(ref) != _record_key(lab):
            raise ValueError(f"record {idx}: position mismatch")
        wdl = lab[37:38]
        changed += int(ref[37:38] != wdl)
        decisive += int(wdl != b"\x00")
        out.append(ref[:37] + wdl)
    _write(args.output, out)
    print(json.dumps({
        "records": rn,
        "labels_changed": changed,
        "changed_pct": 100.0 * changed / max(1, rn),
        "decisive": decisive,
        "position_sha256": _sha_records(out, positions_only=True),
    }))


def cmd_assert_decisive(args: argparse.Namespace) -> None:
    n, body = _read(args.input)
    draws = sum(1 for rec in _records(body) if rec[37] == 0)
    if draws:
        raise ValueError(f"{args.input}: {draws}/{n} gym records are not decisive")
    print(json.dumps({"records": n, "decisive": n}))


def cmd_build_cells(args: argparse.Namespace) -> None:
    if args.gym_mult < 2:
        raise ValueError("gym multiplier must be >= 2")
    on, obody = _read(args.base_onp)
    an, abody = _read(args.base_adj)
    gn, gbody = _read(args.gym)
    if on != an:
        raise ValueError("base label variants have different record counts")
    if on == 0 or gn == 0:
        raise ValueError("base and gym corpora must both be non-empty")
    on_rows = list(_records(obody))
    ad_rows = list(_records(abody))
    gym_rows = list(_records(gbody))
    for idx, (left, right) in enumerate(zip(on_rows, ad_rows)):
        if left[:37] != right[:37]:
            raise ValueError(f"base record {idx}: cells differ by more than WDL")
    base_keys = {_record_key(r) for r in on_rows}
    gym_keys = {_record_key(r) for r in gym_rows}
    overlap = base_keys & gym_keys
    if overlap:
        raise ValueError(f"base and gym overlap on {len(overlap)} positions")
    if len(base_keys) != len(on_rows) or len(gym_keys) != len(gym_rows):
        raise ValueError("duplicate positions inside base or gym corpus")

    unique_on = on_rows + gym_rows
    unique_ad = ad_rows + gym_rows
    repeated_gym = gym_rows * args.gym_mult
    cells = {
        "onp_g1": unique_on,
        "adj_g1": unique_ad,
        f"onp_g{args.gym_mult}": on_rows + repeated_gym,
        f"adj_g{args.gym_mult}": ad_rows + repeated_gym,
    }
    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "base_records": on,
        "gym_unique_records": gn,
        "gym_multiplier_high": args.gym_mult,
        "ordered_unique_position_sha256": _sha_records(unique_on, positions_only=True),
        "base_onp_record_sha256": _sha_records(on_rows),
        "base_adj_record_sha256": _sha_records(ad_rows),
        "gym_record_sha256": _sha_records(gym_rows),
        "cells": {},
    }
    for name, rows in cells.items():
        path = outdir / f"{name}.jnnw"
        _write(path, rows)
        manifest["cells"][name] = {
            "records": len(rows),
            "record_sha256": _sha_records(rows),
            "position_sha256": _sha_records(rows, positions_only=True),
        }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


def cmd_verify_cells(args: argparse.Namespace) -> None:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    outdir = Path(args.out_dir)
    cell_rows: dict[str, list[bytes]] = {}
    for name, expected in manifest["cells"].items():
        n, body = _read(outdir / f"{name}.jnnw")
        rows = list(_records(body))
        cell_rows[name] = rows
        if n != expected["records"]:
            raise ValueError(f"{name}: count mismatch")
        if _sha_records(rows) != expected["record_sha256"]:
            raise ValueError(f"{name}: record hash mismatch")

    mult = int(manifest["gym_multiplier_high"])
    required = {"onp_g1", "adj_g1", f"onp_g{mult}", f"adj_g{mult}"}
    if set(cell_rows) != required:
        raise ValueError(f"unexpected cell set: {sorted(cell_rows)}")
    unique_sets = [{_record_key(r) for r in rows} for rows in cell_rows.values()]
    if any(keys != unique_sets[0] for keys in unique_sets[1:]):
        raise ValueError("DOE cells do not share the same unique positions")
    expected_unique = manifest["base_records"] + manifest["gym_unique_records"]
    if len(unique_sets[0]) != expected_unique:
        raise ValueError(f"unique-position count {len(unique_sets[0])}!={expected_unique}")
    for left, right in (("onp_g1", "adj_g1"), (f"onp_g{mult}", f"adj_g{mult}")):
        if len(cell_rows[left]) != len(cell_rows[right]):
            raise ValueError(f"{left}/{right}: record-count mismatch")
        for idx, (a, b) in enumerate(zip(cell_rows[left], cell_rows[right])):
            if a[:37] != b[:37]:
                raise ValueError(f"{left}/{right} record {idx}: differs by more than WDL")
    print(json.dumps({"verified_cells": sorted(manifest["cells"]), "unique_positions": expected_unique}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("subset-fen")
    p.add_argument("--input", required=True); p.add_argument("--output", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--count", type=int); mode.add_argument("--per-group", type=int)
    p.set_defaults(func=cmd_subset_fen)

    p = sub.add_parser("fen-to-jnnw")
    p.add_argument("--input", required=True); p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_fen_to_jnnw)

    p = sub.add_parser("sample")
    p.add_argument("--input", required=True); p.add_argument("--output", required=True)
    p.add_argument("--count", type=int, required=True); p.add_argument("--exclude-fen", action="append")
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("split")
    p.add_argument("--input", required=True); p.add_argument("--prefix", required=True)
    p.add_argument("--shards", type=int, required=True)
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("merge")
    p.add_argument("--prefix", required=True); p.add_argument("--output", required=True)
    p.add_argument("--shards", type=int, required=True); p.add_argument("--source-prefix")
    p.add_argument("--expected", type=int)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("normalize-labels")
    p.add_argument("--reference", required=True); p.add_argument("--relabeled", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_normalize_labels)

    p = sub.add_parser("assert-decisive")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_assert_decisive)

    p = sub.add_parser("build-cells")
    p.add_argument("--base-onp", required=True); p.add_argument("--base-adj", required=True)
    p.add_argument("--gym", required=True); p.add_argument("--gym-mult", type=int, required=True)
    p.add_argument("--out-dir", required=True); p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_build_cells)

    p = sub.add_parser("verify-cells")
    p.add_argument("--out-dir", required=True); p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_verify_cells)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (OSError, ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
