#!/usr/bin/env python3
"""Generate the canonical data-free T3/F6 zero-residual V4 probe artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
RF1_SHA = "0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"


def zero_matrix(rows: int, cols: int) -> list[list[int]]:
    return [[0 for _ in range(cols)] for _ in range(rows)]


def payload() -> dict[str, object]:
    return {
        "architecture": {
            "hidden": [256, 128, 64],
            "linear_output": True,
            "relu_hidden": True,
        },
        "arm": "T3_F6_ONLY",
        "base": "byte-identical T0 parent score, coefficient 1",
        "input_names": [f"F6_ALL_NEW_{i:02d}" for i in range(66)],
        "input_semantics": "exact frozen F6_ALL_NEW packed order",
        "input_width": 66,
        "normalization": {"mean": [0] * 66, "std": [1] * 66},
        "params": {
            "W0": zero_matrix(66, 256),
            "W1": zero_matrix(256, 128),
            "W2": zero_matrix(128, 64),
            "W3": zero_matrix(64, 1),
            "b0": [0] * 256,
            "b1": [0] * 128,
            "b2": [0] * 64,
            "b3": [0],
        },
        "provenance": {
            "d1_sha256": D1_SHA,
            "rf1_sha256": RF1_SHA,
            "t0_sha256": T0_SHA,
        },
        "schema": "jass.t3_rf1_joint_ab.v1",
        "score_convention": "higher_is_better_for_parent",
    }


def canonical_bytes() -> bytes:
    return (json.dumps(payload(), sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--print-sha256", action="store_true")
    args = parser.parse_args()
    raw = canonical_bytes()
    args.out.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if args.print_sha256:
        print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
