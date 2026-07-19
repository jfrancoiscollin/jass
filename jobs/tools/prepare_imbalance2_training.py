#!/usr/bin/env python3
"""Prepare exact-TB and outcome-weighted data for L3-IMBALANCE2."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
from collections import Counter
from pathlib import Path

MAGIC = b"JNNW"
REC_SIZE = 38
REC = struct.Struct("<QQQQBiB")
SAFE_SQUARES = tuple(range(6, 46))
ROLE_POLICY_ENV = "IMBALANCE2_REWEIGHT_POLICY"
ROLE_POLICY_V2 = "role-aware-v2"


def read_jnnw(path: Path) -> list[bytearray]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC_SIZE:
        raise ValueError(f"{path}: size/count mismatch")
    return [bytearray(body[i * REC_SIZE:(i + 1) * REC_SIZE]) for i in range(count)]


def write_jnnw(path: Path, records: list[bytes | bytearray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<I", len(records)) + b"".join(records))


def bits(squares: list[int]) -> int:
    out = 0
    for square in squares:
        out |= 1 << (square - 1)
    return out


def write_jsm1(path: Path, count: int, seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"JSM1")
        handle.write(struct.pack("<I", count))
        for index in range(count):
            digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
            identifier = struct.unpack_from("<Q", digest)[0]
            handle.write(struct.pack("<QQB", identifier, identifier, 1))


def generate_static(args: argparse.Namespace) -> int:
    if args.low not in (1, 2) or args.high != args.low + 2:
        raise ValueError("static exact-TB teacher is restricted to 1v3 and 2v4")
    if args.advantaged_side not in ("W", "B"):
        raise ValueError("advantaged side must be W or B")
    rng = random.Random(args.seed)
    records: list[bytes] = []
    seen: set[bytes] = set()
    attempts = 0
    while len(records) < args.count:
        attempts += 1
        if attempts > args.count * 100:
            raise RuntimeError("could not generate enough unique positions")
        squares = list(SAFE_SQUARES)
        rng.shuffle(squares)
        white_n = args.high if args.advantaged_side == "W" else args.low
        black_n = args.high if args.advantaged_side == "B" else args.low
        wm = squares[:white_n]
        bm = squares[white_n:white_n + black_n]
        stm = len(records) & 1
        rec = REC.pack(bits(wm), 0, bits(bm), 0, stm, 0, 0)
        key = rec[:33]
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)
    write_jnnw(Path(args.out_data), records)
    write_jsm1(Path(args.out_meta), len(records), args.seed)
    report = {
        "schema": 1,
        "mode": "static_exact_tb_source",
        "stratum": f"{args.low}v{args.high}",
        "advantaged_side": args.advantaged_side,
        "records": len(records),
        "unique_positions": len(seen),
        "total_pieces": args.low + args.high,
        "requires_egdb_relabel": True,
        "seed": args.seed,
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


def encode_outcomes(args: argparse.Namespace) -> int:
    records = read_jnnw(Path(args.input))
    counts: Counter[str] = Counter()
    for rec in records:
        stm = rec[32]
        wdl = struct.unpack_from("<b", rec, 37)[0]
        if stm not in (0, 1) or wdl not in (-1, 0, 1):
            raise ValueError("invalid STM/WDL record")
        up_is_stm = (args.advantaged_side == "W" and stm == 0) or (
            args.advantaged_side == "B" and stm == 1
        )
        up_outcome = wdl if up_is_stm else -wdl
        struct.pack_into("<i", rec, 33, up_outcome)
        counts[{1: "win", 0: "draw", -1: "loss"}[up_outcome]] += 1
    write_jnnw(Path(args.output), records)
    report = {
        "schema": 1,
        "mode": "material_up_outcome_code",
        "advantaged_side": args.advantaged_side,
        "records": len(records),
        "score_field_semantics": "material_up_outcome_code_-1_0_1_no_search",
        "counts": dict(counts),
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


def record_role_bucket(rec: bytes | bytearray) -> str:
    """Classify one record for role-aware V2 weighting.

    The specialist domain is exact: two MEN of difference and equal king counts.
    WDL is stored from side-to-move POV, so the role/outcome pair can be read
    without game-history state. Positions outside the exact domain are anchors.
    """
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    wdl = struct.unpack_from("<b", rec, 37)[0]
    if stm not in (0, 1) or wdl not in (-1, 0, 1):
        raise ValueError("invalid STM/WDL record")
    nwm, nwk = wm.bit_count(), wk.bit_count()
    nbm, nbk = bm.bit_count(), bk.bit_count()
    if abs(nwm - nbm) != 2 or nwk != nbk:
        return "anchor_outside_exact_2men_equal_kings"
    up_colour = 0 if nwm > nbm else 1
    role = "up" if stm == up_colour else "down"
    outcome = {1: "win", 0: "draw", -1: "loss"}[wdl]
    return f"{role}_{outcome}"


def role_bucket_weight(bucket: str, expected: float, draw: float, upset: float) -> float:
    if bucket.startswith("anchor_"):
        return expected
    if bucket in ("up_draw", "down_draw"):
        return draw
    if bucket in ("up_win", "down_loss"):
        return expected
    if bucket in ("up_loss", "down_win"):
        return upset
    raise ValueError(f"unknown role bucket: {bucket}")


def _validate_reweight(args: argparse.Namespace, records: list[bytearray]) -> tuple[int, int]:
    n = len(records)
    if not 0 <= args.holdout_count < n:
        raise ValueError("invalid holdout count")
    train_n = n - args.holdout_count
    codes = [struct.unpack_from("<i", rec, 33)[0] for rec in records[:train_n]]
    if any(code not in (-1, 0, 1) for code in codes):
        raise ValueError("score field is not a material-up outcome code")
    if not (0 < args.win_weight < args.draw_weight < args.loss_weight):
        raise ValueError("require 0 < win_weight < draw_weight < loss_weight")
    return n, train_n


def reweight_material_up_v1(args: argparse.Namespace, records: list[bytearray]) -> int:
    n, train_n = _validate_reweight(args, records)
    codes = [struct.unpack_from("<i", rec, 33)[0] for rec in records[:train_n]]
    class_weight = {1: args.win_weight, 0: args.draw_weight, -1: args.loss_weight}
    weights = [class_weight[code] for code in codes]
    rng = random.Random(args.seed)
    sampled = rng.choices(range(train_n), weights=weights, k=train_n)
    out = [records[index] for index in sampled]
    if args.holdout_count:
        out.extend(records[train_n:])
    write_jnnw(Path(args.output), out)
    source_counts = Counter(codes)
    sampled_counts = Counter(codes[index] for index in sampled)
    report = {
        "schema": 1,
        "mode": "deterministic_weighted_resample",
        "policy": "material-up-v1",
        "records_total": n,
        "training_records": train_n,
        "holdout_records_untouched": args.holdout_count,
        "weights_material_up_pov": {
            "win": args.win_weight,
            "draw": args.draw_weight,
            "loss": args.loss_weight,
        },
        "source_training_counts": {"win": source_counts[1], "draw": source_counts[0], "loss": source_counts[-1]},
        "resampled_training_counts": {"win": sampled_counts[1], "draw": sampled_counts[0], "loss": sampled_counts[-1]},
        "seed": args.seed,
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


def reweight_role_v2(args: argparse.Namespace, records: list[bytearray]) -> int:
    n, train_n = _validate_reweight(args, records)
    buckets = [record_role_bucket(rec) for rec in records[:train_n]]
    weights = [
        role_bucket_weight(bucket, args.win_weight, args.draw_weight, args.loss_weight)
        for bucket in buckets
    ]
    rng = random.Random(args.seed)
    sampled = rng.choices(range(train_n), weights=weights, k=train_n)
    out = [records[index] for index in sampled]
    if args.holdout_count:
        out.extend(records[train_n:])
    write_jnnw(Path(args.output), out)
    source_counts = Counter(buckets)
    sampled_counts = Counter(buckets[index] for index in sampled)
    domain_records = sum(count for bucket, count in source_counts.items() if not bucket.startswith("anchor_"))
    if domain_records == 0:
        raise ValueError("role-aware-v2 found no exact two-men/equal-kings training record")
    report = {
        "schema": 2,
        "mode": "deterministic_role_domain_resample",
        "policy": ROLE_POLICY_V2,
        "records_total": n,
        "training_records": train_n,
        "holdout_records_untouched": args.holdout_count,
        "domain": {
            "men_gap": 2,
            "equal_king_counts": True,
            "classification": "per_position_current_material_and_side_to_move",
            "records": domain_records,
            "outside_domain_anchor_records": train_n - domain_records,
        },
        "weight_semantics": {
            "expected_result": args.win_weight,
            "draw": args.draw_weight,
            "upset_result": args.loss_weight,
            "matrix_side_to_move_pov": {
                "up": {"win": args.win_weight, "draw": args.draw_weight, "loss": args.loss_weight},
                "down": {"win": args.loss_weight, "draw": args.draw_weight, "loss": args.win_weight},
            },
            "outside_domain_anchor": args.win_weight,
        },
        "source_training_buckets": dict(sorted(source_counts.items())),
        "resampled_training_buckets": dict(sorted(sampled_counts.items())),
        "score_field_used_for_weighting": False,
        "wdl_field_semantics": "side_to_move_pov_-1_0_1",
        "per_move_criticality_relabel": False,
        "seed": args.seed,
    }
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


def reweight(args: argparse.Namespace) -> int:
    records = read_jnnw(Path(args.input))
    policy = os.environ.get(ROLE_POLICY_ENV, "material-up-v1")
    if policy == "material-up-v1":
        return reweight_material_up_v1(args, records)
    if policy == ROLE_POLICY_V2:
        return reweight_role_v2(args, records)
    raise ValueError(f"unsupported {ROLE_POLICY_ENV}={policy}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    static = sub.add_parser("static")
    static.add_argument("--low", type=int, required=True)
    static.add_argument("--high", type=int, required=True)
    static.add_argument("--advantaged-side", choices=("W", "B"), required=True)
    static.add_argument("--count", type=int, required=True)
    static.add_argument("--seed", type=int, required=True)
    static.add_argument("--out-data", required=True)
    static.add_argument("--out-meta", required=True)
    static.add_argument("--report", required=True)
    static.set_defaults(func=generate_static)

    encode = sub.add_parser("encode")
    encode.add_argument("--input", required=True)
    encode.add_argument("--output", required=True)
    encode.add_argument("--advantaged-side", choices=("W", "B"), required=True)
    encode.add_argument("--report", required=True)
    encode.set_defaults(func=encode_outcomes)

    rw = sub.add_parser("reweight")
    rw.add_argument("--input", required=True)
    rw.add_argument("--output", required=True)
    rw.add_argument("--holdout-count", type=int, required=True)
    rw.add_argument("--win-weight", type=float, default=1.0)
    rw.add_argument("--draw-weight", type=float, default=2.0)
    rw.add_argument("--loss-weight", type=float, default=4.0)
    rw.add_argument("--seed", type=int, required=True)
    rw.add_argument("--report", required=True)
    rw.set_defaults(func=reweight)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
