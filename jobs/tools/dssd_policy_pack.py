#!/usr/bin/env python3
"""Pack a frozen jass.deep_sibling_policy.v1 policy for native runtime use.

This tool performs serialization only. It does not fit, normalize, rescale,
clip, calibrate, or otherwise transform the 126 frozen weights in either
colour bank.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

MAGIC = "JASS_DSSD_MOVE_ORDER_POLICY_V1"
SOURCE_SCHEMA = "jass.deep_sibling_policy.v1"
MOVE_FEATURES = [
    "num_captures",
    "captured_kings",
    "promotes",
    "moving_king",
    "from_norm",
    "to_norm",
]


def validate(payload: dict) -> tuple[list[float], list[float]]:
    if payload.get("schema") != SOURCE_SCHEMA:
        raise ValueError("policy schema drift")
    if payload.get("usable") is not True:
        raise ValueError("policy is not marked usable")
    if payload.get("eval_feature_width") != 120:
        raise ValueError("expected exactly 120 eval features")
    if payload.get("move_feature_names") != MOVE_FEATURES:
        raise ValueError("move feature order drift")
    if payload.get("score_convention") != "higher_is_better_for_parent":
        raise ValueError("score convention drift")

    weights = payload.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("missing weights")

    banks: list[list[float]] = []
    for name in ("white_parent", "black_parent"):
        raw = weights.get(name)
        if not isinstance(raw, list) or len(raw) != 126:
            raise ValueError(f"{name}: expected 126 weights")
        bank: list[float] = []
        for value in raw:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name}: non-numeric weight")
            x = float(value)
            if not math.isfinite(x):
                raise ValueError(f"{name}: non-finite weight")
            bank.append(x)
        banks.append(bank)
    return banks[0], banks[1]


def pack(payload: dict) -> bytes:
    white, black = validate(payload)
    lines = [MAGIC, "120 6"]
    # repr(float) is the shortest Python decimal that round-trips to the exact
    # IEEE-754 value. There is deliberately no arithmetic transformation here.
    lines.append(" ".join(repr(x) for x in white))
    lines.append(" ".join(repr(x) for x in black))
    return ("\n".join(lines) + "\n").encode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()

    try:
        raw_source = args.input.read_bytes()
        payload = json.loads(raw_source.decode("utf-8"))
        packed = pack(payload)
        args.output.write_bytes(packed)
        if args.receipt:
            receipt = {
                "schema": "jass.dssd_move_order_policy_pack.v1",
                "source_schema": payload.get("schema"),
                "source_sha256": hashlib.sha256(raw_source).hexdigest(),
                "packed_sha256": hashlib.sha256(packed).hexdigest(),
                "eval_feature_width": 120,
                "move_feature_width": 6,
                "total_feature_width": 126,
                "move_feature_names": MOVE_FEATURES,
                "score_convention": "higher_is_better_for_parent",
                "serialization_only": True,
                "weight_transform": "none",
            }
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"DSSD_POLICY_PACK_ERROR: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
