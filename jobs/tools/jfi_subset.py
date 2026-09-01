#!/usr/bin/env python3
"""Materialize a bounded aligned CURRENT prefix for JFI timing only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

JNNW_RECORD_SIZE = 38
MAX_RECORDS = 20_000


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_bytes(source, target, count):
    remaining = count
    while remaining:
        block = source.read(min(1 << 20, remaining))
        if not block:
            raise ValueError("source truncated")
        target.write(block)
        remaining -= len(block)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--target-values", required=True)
    ap.add_argument("--records", required=True, type=int)
    ap.add_argument("--holdout-count", required=True, type=int)
    ap.add_argument("--out-data", required=True)
    ap.add_argument("--out-feat", required=True)
    ap.add_argument("--out-target-values", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)
    if not 1 <= args.records <= MAX_RECORDS:
        raise SystemExit(f"--records must be in [1,{MAX_RECORDS}]")
    if not 0 < args.holdout_count < args.records:
        raise SystemExit("invalid subset holdout count")

    data = Path(args.data)
    with data.open("rb") as stream:
        header = stream.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise SystemExit("invalid JNNW")
    total = struct.unpack_from("<I", header, 4)[0]
    if total < args.records or data.stat().st_size != 8 + total * JNNW_RECORD_SIZE:
        raise SystemExit("JNNW count/size drift")

    feat = Path(args.feat)
    with feat.open("rb") as stream:
        fheader = stream.read(12)
    if len(fheader) != 12 or fheader[:4] != b"FEAT":
        raise SystemExit("invalid FEAT")
    feat_rows, width = struct.unpack_from("<II", fheader, 4)
    if feat_rows != total or feat.stat().st_size != 12 + total * width * 4:
        raise SystemExit("FEAT count/size drift")

    targets = np.load(args.target_values, allow_pickle=False, mmap_mode="r")
    if targets.dtype != np.float32 or targets.shape != (total,):
        raise SystemExit("target alignment/dtype drift")

    out_data = Path(args.out_data)
    out_data.parent.mkdir(parents=True, exist_ok=True)
    with data.open("rb") as src, out_data.open("wb") as dst:
        src.read(8)
        dst.write(b"JNNW" + struct.pack("<I", args.records))
        copy_bytes(src, dst, args.records * JNNW_RECORD_SIZE)

    out_feat = Path(args.out_feat)
    with feat.open("rb") as src, out_feat.open("wb") as dst:
        src.read(12)
        dst.write(b"FEAT" + struct.pack("<II", args.records, width))
        copy_bytes(src, dst, args.records * width * 4)

    out_targets = Path(args.out_target_values)
    np.save(out_targets, np.asarray(targets[:args.records], dtype=np.float32), allow_pickle=False)
    payload = {
        "schema": "jass.jfi.technical_subset.v1",
        "role": "consumed_prefix_timing_only",
        "records": args.records,
        "train_records": args.records - args.holdout_count,
        "holdout_records": args.holdout_count,
        "inputs": {
            "data_sha256": sha256_file(data),
            "feat_sha256": sha256_file(feat),
            "target_sha256": sha256_file(args.target_values),
        },
        "outputs": {
            "data_sha256": sha256_file(out_data),
            "feat_sha256": sha256_file(out_feat),
            "target_sha256": sha256_file(out_targets),
        },
        "markers": {
            "FULL_FITS": 0,
            "FRESH_OPENINGS": 0,
            "STRENGTH_GAMES": 0,
            "SCIENTIFIC_DECISION": False,
            "SCAN_WEIGHT_READS": 0,
            "SCAN_SCORE_READS": 0,
        },
    }
    Path(args.manifest).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
