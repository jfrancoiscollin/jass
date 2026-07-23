#!/usr/bin/env python3
"""Create a deterministic convex blend of two PJTW v3 evaluations.

The output weights are ``alpha_a * A + (1-alpha_a) * B`` rounded to the
nearest integer (NumPy's deterministic ties-to-even rule). Legacy v3 and
self-describing v3 headers are accepted. Both parents must have the exact same
PJTW header and no trailing payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np

HDR = 20
VERSION_MASK = 0xFF
KNOWN_VERSION_BITS = VERSION_MASK | 0x100 | 0x200


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> tuple[tuple[int, int, int, int, int], np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < HDR:
        raise ValueError(f"{path}: truncated PJTW header")
    header = struct.unpack("<5I", raw[:HDR])
    magic, version, _scale, n_pat, n_ext = header
    if magic != 0x57544A50:
        raise ValueError(f"{path}: bad PJTW magic 0x{magic:08x}")
    if version & ~KNOWN_VERSION_BITS:
        raise ValueError(f"{path}: PJTW version {version} has unknown marker bits")
    if (version & VERSION_MASK) != 3:
        raise ValueError(f"{path}: PJTW version {version}; expected base v3")
    total = 2 * (n_pat + n_ext)
    expected = HDR + total * 4
    if len(raw) != expected:
        raise ValueError(f"{path}: size {len(raw)} != expected {expected} (trailing or truncated data)")
    weights = np.frombuffer(raw, dtype="<i4", count=total, offset=HDR).astype(np.float64)
    return header, weights


def blend(parent_a: Path, parent_b: Path, alpha_a: float, out: Path) -> dict:
    if not 0.0 <= alpha_a <= 1.0:
        raise ValueError("alpha-a must be in [0,1]")
    header_a, weights_a = load(parent_a)
    header_b, weights_b = load(parent_b)
    if header_a != header_b:
        raise ValueError(f"PJTW headers differ: {header_a} != {header_b}")
    alpha_b = 1.0 - alpha_a
    merged = np.rint(alpha_a * weights_a + alpha_b * weights_b)
    merged = merged.clip(-(2**31), 2**31 - 1).astype("<i4")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(struct.pack("<5I", *header_a) + merged.tobytes())
    changed_from_a = int(np.count_nonzero(merged.astype(np.int64) != weights_a.astype(np.int64)))
    changed_from_b = int(np.count_nonzero(merged.astype(np.int64) != weights_b.astype(np.int64)))
    return {
        "schema": 1,
        "mode": "convex-weight-interpolation",
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "parent_a": str(parent_a),
        "parent_b": str(parent_b),
        "parent_a_sha256": sha256(parent_a),
        "parent_b_sha256": sha256(parent_b),
        "output": str(out),
        "output_sha256": sha256(out),
        "header": {
            "magic": header_a[0],
            "version": header_a[1],
            "scale": header_a[2],
            "n_pat": header_a[3],
            "n_ext": header_a[4],
        },
        "weight_count": int(merged.size),
        "weights_changed_from_a": changed_from_a,
        "weights_changed_from_b": changed_from_b,
        "training_records": 0,
        "self_play_games": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-a", required=True, type=Path)
    parser.add_argument("--parent-b", required=True, type=Path)
    parser.add_argument("--alpha-a", required=True, type=float)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = blend(args.parent_a, args.parent_b, args.alpha_a, args.out)
    except (OSError, ValueError, struct.error) as exc:
        print(f"blend_pjtw: {exc}", file=sys.stderr)
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
