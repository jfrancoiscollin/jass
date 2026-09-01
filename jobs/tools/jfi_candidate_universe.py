#!/usr/bin/env python3
"""Freeze an exact target-blind JFI candidate universe from Jass self-play."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
JSM1_DTYPE = np.dtype([("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1")])
JSM2_DTYPE = np.dtype([
    ("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1"),
    ("ply", "<u2"), ("game_plies", "<u2"), ("last_eps_ply", "<u2"),
    ("game_result", "i1"), ("flags", "u1"),
])
STATE_FIELDS = ("wm", "wk", "bm", "bk", "stm")
MASK64 = np.uint64(0xFFFFFFFFFFFFFFFF)
UNIVERSE_HASH_SCHEMA = "splitmix64(source_index,state_fields); no seed"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def open_counted(path, magics):
    with open(path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] not in magics:
        raise ValueError(f"{path}: unexpected counted-file magic")
    count = struct.unpack_from("<I", header, 4)[0]
    dtype = magics[header[:4]]
    if Path(path).stat().st_size != 8 + count * dtype.itemsize:
        raise ValueError(f"{path}: size/count drift")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(count,)), header[:4]


def splitmix64(values):
    with np.errstate(over="ignore"):
        z = np.asarray(values, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def target_blind_hash(source_indices, rows):
    value = splitmix64(np.asarray(source_indices, dtype=np.uint64))
    for position, field in enumerate(STATE_FIELDS):
        component = np.asarray(rows[field], dtype=np.uint64)
        value = splitmix64(value ^ component ^ np.uint64(0xD6E8FEB86659FD93 + position))
    return value


def select_smallest_hashes(hashes, count):
    hashes = np.asarray(hashes, dtype=np.uint64)
    if not 0 < count <= len(hashes):
        raise ValueError("candidate count must be in [1, source rows]")
    if count == len(hashes):
        return np.arange(count, dtype=np.int64)
    partition = np.argpartition(hashes, count - 1)[:count]
    threshold = np.max(hashes[partition])
    lower = np.flatnonzero(hashes < threshold)
    equal = np.flatnonzero(hashes == threshold)
    needed = count - len(lower)
    selected = np.concatenate((lower, equal[:needed])).astype(np.int64, copy=False)
    if len(selected) != count:
        raise AssertionError("exact candidate count construction failed")
    return selected


def write_counted(path, magic, rows, indices, *, zero_labels=False, chunk=200_000):
    path = Path(path)
    with path.open("wb") as handle:
        handle.write(magic + struct.pack("<I", len(indices)))
        for start in range(0, len(indices), chunk):
            chosen = np.asarray(rows[indices[start:start + chunk]])
            if zero_labels:
                clean = np.empty(len(chosen), dtype=JNNW_DTYPE)
                for field in STATE_FIELDS:
                    clean[field] = chosen[field]
                clean["score"] = 0
                clean["wdl"] = 0
                chosen = clean
            elif magic == b"JSM1" and chosen.dtype != JSM1_DTYPE:
                clean = np.empty(len(chosen), dtype=JSM1_DTYPE)
                for field in JSM1_DTYPE.names:
                    clean[field] = chosen[field]
                chosen = clean
            handle.write(np.ascontiguousarray(chosen).tobytes())


def build_universe(args):
    data, _ = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    meta, _ = open_counted(args.meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE})
    if len(meta) != len(data):
        raise ValueError("data/meta alignment drift")
    if args.expected_data_sha and sha256_file(args.data) != args.expected_data_sha:
        raise ValueError("source data SHA drift")
    if args.expected_meta_sha and sha256_file(args.meta) != args.expected_meta_sha:
        raise ValueError("source metadata SHA drift")
    hashes = np.empty(len(data), dtype=np.uint64)
    for start in range(0, len(data), args.chunk):
        stop = min(start + args.chunk, len(data))
        indices = np.arange(start, stop, dtype=np.uint64)
        hashes[start:stop] = target_blind_hash(indices, data[start:stop])
    chosen = select_smallest_hashes(hashes, args.records)
    opening = np.asarray(meta[chosen]["opening_id"], dtype=np.uint64)
    role_hash = splitmix64(opening ^ np.uint64(args.split_seed))
    dev = role_hash % np.uint64(args.dev_mod) == 0
    train_indices = chosen[~dev]
    dev_indices = chosen[dev]
    ordered = np.concatenate((train_indices, dev_indices)).astype(np.int64, copy=False)
    write_counted(args.out_data, b"JNNW", data, ordered, zero_labels=True, chunk=args.chunk)
    write_counted(args.out_meta, b"JSM1", meta, ordered, chunk=args.chunk)
    np.save(args.origin_indices_out, ordered.astype(np.uint32), allow_pickle=False)
    np.save(args.roles_out, np.concatenate((
        np.zeros(len(train_indices), dtype=np.uint8),
        np.ones(len(dev_indices), dtype=np.uint8),
    )), allow_pickle=False)
    report = {
        "schema": "jass.jfi.candidate_universe.v1",
        "source": {
            "data": str(args.data), "meta": str(args.meta), "records": len(data),
            "data_sha256": sha256_file(args.data), "meta_sha256": sha256_file(args.meta),
        },
        "selection": {
            "algorithm": UNIVERSE_HASH_SCHEMA,
            "records": len(ordered), "train_candidates": len(train_indices),
            "dev_eval": len(dev_indices), "train_first_dev_tail": True,
        },
        "split": {
            "unit": "opening_id", "seed": args.split_seed, "dev_mod": args.dev_mod,
            "all_rows_of_opening_share_role": True,
        },
        "files": {
            "data": {"path": str(args.out_data), "sha256": sha256_file(args.out_data)},
            "meta": {"path": str(args.out_meta), "sha256": sha256_file(args.out_meta)},
            "origin_indices": {
                "path": str(args.origin_indices_out), "sha256": sha256_file(args.origin_indices_out),
            },
            "roles": {"path": str(args.roles_out), "sha256": sha256_file(args.roles_out)},
        },
        "guards": {
            "source_score_values_read": 0, "source_wdl_values_read": 0,
            "output_score_nonzero": 0, "output_wdl_nonzero": 0,
            "TARGET_READS": 0, "SCAN_READS": 0,
        },
    }
    Path(args.manifest).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--expected-data-sha")
    ap.add_argument("--expected-meta-sha")
    ap.add_argument("--records", type=int, default=10_000_000)
    ap.add_argument("--split-seed", type=int, default=2026120102)
    ap.add_argument("--dev-mod", type=int, default=10)
    ap.add_argument("--chunk", type=int, default=200_000)
    ap.add_argument("--out-data", required=True)
    ap.add_argument("--out-meta", required=True)
    ap.add_argument("--origin-indices-out", required=True)
    ap.add_argument("--roles-out", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)
    if args.records != 10_000_000 and argv is None:
        raise SystemExit("production JFI candidate universe must contain exactly 10,000,000 rows")
    if args.split_seed != 2026120102 or args.dev_mod != 10:
        raise SystemExit("JFI-C split contract drift")
    build_universe(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
