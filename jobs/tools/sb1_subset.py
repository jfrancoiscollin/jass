#!/usr/bin/env python3
"""Materialize a bounded prefix of already-consumed SB1 CURRENT data for timing only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

JNNW_RECORD_SIZE = 38


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def copy_exact(source, target, count):
    remaining = count
    while remaining:
        block = source.read(min(1 << 20, remaining))
        if not block:
            raise ValueError("source truncated while materializing subset")
        target.write(block)
        remaining -= len(block)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--target-values", required=True)
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--holdout-count", type=int, required=True)
    parser.add_argument("--out-data", required=True)
    parser.add_argument("--out-feat", required=True)
    parser.add_argument("--out-target-values", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    if not 1 <= args.records < 2_000_000:
        raise SystemExit("--records must be bounded below full CURRENT_2M")
    if not 0 < args.holdout_count < args.records:
        raise SystemExit("invalid subset holdout count")

    data = Path(args.data)
    with data.open("rb") as stream:
        head = stream.read(8)
    if len(head) != 8 or head[:4] != b"JNNW":
        raise SystemExit("invalid JNNW")
    total = struct.unpack_from("<I", head, 4)[0]
    if total < args.records:
        raise SystemExit("requested subset exceeds input records")
    if data.stat().st_size != 8 + total * JNNW_RECORD_SIZE:
        raise SystemExit("JNNW size/count drift")

    feat = Path(args.feat)
    with feat.open("rb") as stream:
        fhead = stream.read(12)
    if len(fhead) != 12 or fhead[:4] != b"FEAT":
        raise SystemExit("invalid FEAT")
    feat_count, width = struct.unpack_from("<II", fhead, 4)
    if feat_count != total or feat.stat().st_size != 12 + total * width * 4:
        raise SystemExit("FEAT alignment drift")

    target = np.load(args.target_values, allow_pickle=False, mmap_mode="r")
    if not isinstance(target, np.ndarray) or target.dtype != np.float32 or target.shape != (total,):
        raise SystemExit("target sidecar alignment/dtype drift")

    out_data = Path(args.out_data)
    out_data.parent.mkdir(parents=True, exist_ok=True)
    with data.open("rb") as src, out_data.open("wb") as dst:
        src.read(8)
        dst.write(b"JNNW" + struct.pack("<I", args.records))
        copy_exact(src, dst, args.records * JNNW_RECORD_SIZE)

    out_feat = Path(args.out_feat)
    out_feat.parent.mkdir(parents=True, exist_ok=True)
    with feat.open("rb") as src, out_feat.open("wb") as dst:
        src.read(12)
        dst.write(b"FEAT" + struct.pack("<II", args.records, width))
        copy_exact(src, dst, args.records * width * 4)

    out_target = Path(args.out_target_values)
    out_target.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_target, np.asarray(target[:args.records], dtype=np.float32), allow_pickle=False)
    if not out_target.exists():
        raise SystemExit(f"target subset was not created at {out_target}")

    manifest = {
        "schema": "jass.sb1.technical_subset.v1",
        "role": "consumed_prefix_timing_only",
        "records": args.records,
        "train_records": args.records - args.holdout_count,
        "holdout_records": args.holdout_count,
        "row_order": "original_prefix_preserved",
        "inputs": {
            "data": {"path": str(data), "sha256": sha256_file(data), "records": total},
            "feat": {"path": str(feat), "sha256": sha256_file(feat), "width": width},
            "target_values": {"path": str(args.target_values), "sha256": sha256_file(args.target_values)},
        },
        "outputs": {
            "data": {"path": str(out_data), "sha256": sha256_file(out_data)},
            "feat": {"path": str(out_feat), "sha256": sha256_file(out_feat)},
            "target_values": {"path": str(out_target), "sha256": sha256_file(out_target)},
        },
        "markers": {
            "FULL_FITS": 0,
            "FRESH_FORCE": 0,
            "STRENGTH_GAMES": 0,
            "SCIENTIFIC_DECISION": False,
        },
    }
    Path(args.manifest).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
