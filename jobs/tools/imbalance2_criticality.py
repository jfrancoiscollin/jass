#!/usr/bin/env python3
"""Difficulty-aware resampling for the L3 two-pawn imbalance lineage.

The tool deliberately leaves the V1 pipeline untouched.  It profiles a bounded,
deterministically selected subset of training positions by enumerating every legal
child with ``jass --dump-children`` and scoring those children with the frozen
parent evaluation via ``jass --rewrite-scores-with-search``.

A position is considered difficult when several legal moves exist but only a
small number remain within a configurable margin of the best searched child.
The resulting multiplier is combined with the existing material-up outcome
weight (win/draw/loss = 1/2/4 by default), capped, and used for deterministic
fixed-size resampling.  The holdout suffix is copied byte-for-byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

MAGIC = b"JNNW"
REC_SIZE = 38
REC = struct.Struct("<QQQQBiB")


def read_jnnw(path: Path) -> list[bytearray]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC_SIZE:
        raise ValueError(f"{path}: size/count mismatch")
    return [bytearray(body[i * REC_SIZE:(i + 1) * REC_SIZE]) for i in range(count)]


def write_jnnw(path: Path, records: Iterable[bytes | bytearray]) -> int:
    rows = list(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<I", len(rows)) + b"".join(rows))
    return len(rows)


def popcount(value: int) -> int:
    return int(value).bit_count()


def unpack_record(record: bytes | bytearray) -> tuple[int, int, int, int, int, int, int]:
    wm, wk, bm, bk, stm, score, wdl = REC.unpack(record)
    if stm not in (0, 1):
        raise ValueError(f"invalid stm byte {stm}")
    if wdl not in (0, 1, 255):  # struct B exposes -1 as 255
        raise ValueError(f"invalid wdl byte {wdl}")
    signed_wdl = -1 if wdl == 255 else wdl
    return wm, wk, bm, bk, stm, score, signed_wdl


def squares(bits: int) -> list[int]:
    return [index + 1 for index in range(50) if (bits >> index) & 1]


def side_tokens(men: int, kings: int) -> str:
    tokens = [str(square) for square in squares(men)]
    tokens.extend(f"K{square}" for square in squares(kings))
    return ",".join(tokens)


def record_to_fen(record: bytes | bytearray) -> str:
    wm, wk, bm, bk, stm, _score, _wdl = unpack_record(record)
    turn = "W" if stm == 0 else "B"
    return f"{turn}:W{side_tokens(wm, wk)}:B{side_tokens(bm, bk)}"


def expand_square_token(token: str) -> tuple[bool, list[int]]:
    token = token.strip()
    king = token.startswith("K")
    if king:
        token = token[1:]
    if not token:
        return king, []
    if "-" in token:
        left, right = token.split("-", 1)
        start, end = int(left), int(right)
        step = 1 if end >= start else -1
        values = list(range(start, end + step, step))
    else:
        values = [int(token)]
    if any(square < 1 or square > 50 for square in values):
        raise ValueError(f"square outside 1..50 in token {token!r}")
    return king, values


def parse_side_field(field: str, expected: str) -> tuple[int, int]:
    if not field.startswith(expected):
        raise ValueError(f"expected {expected} field, got {field!r}")
    men = 0
    kings = 0
    payload = field[1:]
    if not payload:
        return men, kings
    for token in payload.split(","):
        king, values = expand_square_token(token)
        for square in values:
            bit = 1 << (square - 1)
            if (men | kings) & bit:
                raise ValueError(f"duplicate square {square}")
            if king:
                kings |= bit
            else:
                men |= bit
    return men, kings


def fen_to_record(fen: str, score: int = 0, wdl: int = 0) -> bytes:
    parts = fen.strip().split(":")
    if len(parts) != 3 or parts[0] not in ("W", "B"):
        raise ValueError(f"unsupported Hub FEN {fen!r}")
    wm, wk = parse_side_field(parts[1], "W")
    bm, bk = parse_side_field(parts[2], "B")
    all_planes = (wm, wk, bm, bk)
    occupied = 0
    for plane in all_planes:
        if occupied & plane:
            raise ValueError(f"overlapping pieces in FEN {fen!r}")
        occupied |= plane
    stm = 0 if parts[0] == "W" else 1
    if wdl not in (-1, 0, 1):
        raise ValueError("wdl must be -1, 0 or 1")
    return REC.pack(wm, wk, bm, bk, stm, int(score), wdl & 0xFF)


def exact_two_man_domain(record: bytes | bytearray, tb_lock_pieces: int) -> bool:
    wm, wk, bm, bk, _stm, _score, _wdl = unpack_record(record)
    men_diff = abs(popcount(wm) - popcount(bm))
    kings_equal = popcount(wk) == popcount(bk)
    total = popcount(wm | wk | bm | bk)
    return men_diff == 2 and kings_equal and total > tb_lock_pieces


def role_of_stm(record: bytes | bytearray) -> str:
    wm, wk, bm, bk, stm, _score, _wdl = unpack_record(record)
    white_material = popcount(wm) + 3 * popcount(wk)
    black_material = popcount(bm) + 3 * popcount(bk)
    if white_material == black_material:
        return "neutral"
    white_up = white_material > black_material
    stm_white = stm == 0
    return "conversion" if white_up == stm_white else "resilience"


def weighted_without_replacement(indices: list[int], weights: list[float], count: int,
                                 seed: int) -> list[int]:
    if count >= len(indices):
        return sorted(indices)
    rng = random.Random(seed)
    ranked: list[tuple[float, int]] = []
    for index, weight in zip(indices, weights, strict=True):
        if weight <= 0:
            raise ValueError("selection weights must be positive")
        # Efraimidis-Spirakis exponential keys: smaller is selected first.
        key = -math.log(max(rng.random(), 1e-300)) / weight
        ranked.append((key, index))
    ranked.sort()
    return sorted(index for _key, index in ranked[:count])


def cmd_make_parents(args: argparse.Namespace) -> int:
    records = read_jnnw(Path(args.input))
    if not 0 <= args.holdout_count < len(records):
        raise ValueError("invalid holdout count")
    train_n = len(records) - args.holdout_count
    eligible: list[int] = []
    selection_weights: list[float] = []
    role_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    code_weight = {1: args.win_weight, 0: args.draw_weight, -1: args.loss_weight}
    for index, record in enumerate(records[:train_n]):
        if not exact_two_man_domain(record, args.tb_lock_pieces):
            continue
        code = struct.unpack_from("<i", record, 33)[0]
        if code not in code_weight:
            raise ValueError(f"record {index}: score field is not material-up outcome code")
        eligible.append(index)
        selection_weights.append(code_weight[code])
        role_counts[role_of_stm(record)] += 1
        outcome_counts[{1: "up_win", 0: "draw", -1: "up_loss"}[code]] += 1

    target = len(eligible) if args.max_parents <= 0 else min(args.max_parents, len(eligible))
    selected = weighted_without_replacement(eligible, selection_weights, target, args.seed)
    out_fen = Path(args.out_fen)
    out_fen.parent.mkdir(parents=True, exist_ok=True)
    out_fen.write_text("".join(record_to_fen(records[index]) + "\n" for index in selected))
    payload = {
        "schema": 1,
        "mode": "imbalance2_criticality_parent_selection",
        "input": str(Path(args.input)),
        "records_total": len(records),
        "training_records": train_n,
        "holdout_records_excluded": args.holdout_count,
        "domain": {
            "absolute_man_difference": 2,
            "equal_king_count": True,
            "tb_lock_max_total_pieces": args.tb_lock_pieces,
        },
        "eligible_parents": len(eligible),
        "selected_parents": len(selected),
        "max_parents": args.max_parents,
        "selection": "deterministic_weighted_without_replacement_by_v1_1_2_4",
        "selection_weights": {
            "material_up_win": args.win_weight,
            "draw": args.draw_weight,
            "material_up_loss": args.loss_weight,
        },
        "eligible_role_counts": dict(role_counts),
        "eligible_outcome_counts": dict(outcome_counts),
        "record_indices": selected,
        "seed": args.seed,
    }
    Path(args.out_index).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def cmd_flatten_children(args: argparse.Namespace) -> int:
    parent_manifest = json.loads(Path(args.parent_index).read_text())
    parent_indices = parent_manifest.get("record_indices")
    if not isinstance(parent_indices, list) or any(not isinstance(value, int) for value in parent_indices):
        raise ValueError("parent index manifest has no integer record_indices list")
    lines = Path(args.children_jsonl).read_text().splitlines()
    if len(lines) != len(parent_indices):
        raise ValueError(f"children line count {len(lines)} != parent count {len(parent_indices)}")

    child_records: list[bytes] = []
    entries: list[dict[str, object]] = []
    move_count_hist: Counter[int] = Counter()
    for line_no, (record_index, line) in enumerate(zip(parent_indices, lines, strict=True)):
        row = json.loads(line)
        if row is None or not isinstance(row, list):
            raise ValueError(f"line {line_no}: expected JSON array from --dump-children")
        start = len(child_records)
        moves: list[str] = []
        for child in row:
            if not isinstance(child, dict) or not isinstance(child.get("fen"), str):
                raise ValueError(f"line {line_no}: malformed child entry")
            child_records.append(fen_to_record(child["fen"]))
            moves.append(str(child.get("move", "")))
        move_count_hist[len(row)] += 1
        entries.append({
            "record_index": record_index,
            "child_start": start,
            "child_count": len(row),
            "moves": moves,
        })

    count = write_jnnw(Path(args.out_data), child_records)
    payload = {
        "schema": 1,
        "mode": "imbalance2_criticality_child_index",
        "parents": len(entries),
        "children": count,
        "move_count_histogram": {str(key): value for key, value in sorted(move_count_hist.items())},
        "entries": entries,
    }
    Path(args.out_index).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def cmd_merge_jnnw(args: argparse.Namespace) -> int:
    merged: list[bytearray] = []
    counts: dict[str, int] = {}
    for raw_path in args.input:
        path = Path(raw_path)
        rows = read_jnnw(path)
        merged.extend(rows)
        counts[str(path)] = len(rows)
    total = write_jnnw(Path(args.output), merged)
    payload = {
        "schema": 1,
        "mode": "ordered_jnnw_merge",
        "inputs": counts,
        "records": total,
    }
    Path(args.report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def classify_criticality(scores: list[int], args: argparse.Namespace) -> tuple[str, float, dict[str, object]]:
    legal = len(scores)
    if legal <= 1:
        return "forced_or_terminal", 1.0, {
            "legal_moves": legal,
            "preserving_moves": legal,
            "best_score": scores[0] if scores else None,
            "second_score": None,
            "best_second_gap": None,
        }
    ordered = sorted(scores, reverse=True)
    best = ordered[0]
    second = ordered[1]
    gap = best - second
    preserving = sum(score >= best - args.preserve_margin for score in ordered)
    ratio = preserving / legal
    if preserving == 1 and gap >= args.unique_gap:
        bucket, multiplier = "unique", args.unique_multiplier
    elif ratio <= args.narrow_ratio and gap >= args.narrow_gap:
        bucket, multiplier = "narrow", args.narrow_multiplier
    elif ratio <= args.contested_ratio:
        bucket, multiplier = "contested", args.contested_multiplier
    else:
        bucket, multiplier = "broad", 1.0
    return bucket, multiplier, {
        "legal_moves": legal,
        "preserving_moves": preserving,
        "preserving_ratio": ratio,
        "best_score": best,
        "second_score": second,
        "best_second_gap": gap,
    }


def sha256_bytes(rows: Iterable[bytes | bytearray]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row)
    return digest.hexdigest()


def cmd_reweight(args: argparse.Namespace) -> int:
    records = read_jnnw(Path(args.input))
    scored_children = read_jnnw(Path(args.scored_children))
    child_manifest = json.loads(Path(args.child_index).read_text())
    entries = child_manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("child index has no entries list")
    expected_children = sum(int(entry["child_count"]) for entry in entries)
    if expected_children != len(scored_children):
        raise ValueError(f"child index expects {expected_children}, scored file has {len(scored_children)}")
    if not 0 <= args.holdout_count < len(records):
        raise ValueError("invalid holdout count")
    train_n = len(records) - args.holdout_count

    base_weights = {1: args.win_weight, 0: args.draw_weight, -1: args.loss_weight}
    if not (0 < args.win_weight < args.draw_weight < args.loss_weight):
        raise ValueError("require 0 < win_weight < draw_weight < loss_weight")
    if args.weight_cap < args.loss_weight:
        raise ValueError("weight cap must be at least the largest base outcome weight")

    weights: list[float] = []
    base_codes: list[int] = []
    for index, record in enumerate(records[:train_n]):
        code = struct.unpack_from("<i", record, 33)[0]
        if code not in base_weights:
            raise ValueError(f"record {index}: score field is not material-up outcome code")
        base_codes.append(code)
        weights.append(float(base_weights[code]))

    profile_by_index: dict[int, dict[str, object]] = {}
    bucket_counts: Counter[str] = Counter()
    role_bucket_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    multiplier_hist: Counter[str] = Counter()
    for entry in entries:
        record_index = int(entry["record_index"])
        start = int(entry["child_start"])
        count = int(entry["child_count"])
        if not 0 <= record_index < train_n:
            raise ValueError(f"profiled parent index {record_index} outside training prefix")
        if record_index in profile_by_index:
            raise ValueError(f"duplicate profiled parent index {record_index}")
        if start < 0 or count < 0 or start + count > len(scored_children):
            raise ValueError(f"invalid child slice for parent {record_index}")
        parent_scores = []
        for child in scored_children[start:start + count]:
            child_score = struct.unpack_from("<i", child, 33)[0]
            parent_scores.append(-child_score)  # child STM is the parent's opponent
        bucket, multiplier, detail = classify_criticality(parent_scores, args)
        role = role_of_stm(records[record_index])
        effective = min(args.weight_cap, weights[record_index] * multiplier)
        weights[record_index] = effective
        detail.update({
            "record_index": record_index,
            "role": role,
            "bucket": bucket,
            "criticality_multiplier": multiplier,
            "base_outcome_weight": base_weights[base_codes[record_index]],
            "effective_weight": effective,
        })
        profile_by_index[record_index] = detail
        bucket_counts[bucket] += 1
        role_bucket_counts[role][bucket] += 1
        multiplier_hist[f"{multiplier:g}"] += 1

    rng = random.Random(args.seed)
    sampled = rng.choices(range(train_n), weights=weights, k=train_n)
    output = [records[index] for index in sampled]
    holdout = records[train_n:]
    output.extend(holdout)
    write_jnnw(Path(args.output), output)

    source_code_counts = Counter(base_codes)
    sampled_code_counts = Counter(base_codes[index] for index in sampled)
    effective_hist = Counter(f"{weight:g}" for weight in weights)
    sampled_bucket_counts = Counter(
        str(profile_by_index.get(index, {}).get("bucket", "unprofiled")) for index in sampled
    )
    holdout_hash = sha256_bytes(holdout)
    output_holdout_hash = sha256_bytes(output[train_n:])
    if holdout_hash != output_holdout_hash:
        raise RuntimeError("holdout changed during criticality reweighting")

    payload = {
        "schema": 1,
        "mode": "deterministic_outcome_x_criticality_resample",
        "records_total": len(records),
        "training_records": train_n,
        "holdout_records_untouched": args.holdout_count,
        "holdout_body_sha256_before": holdout_hash,
        "holdout_body_sha256_after": output_holdout_hash,
        "base_weights_material_up_pov": {
            "win": args.win_weight,
            "draw": args.draw_weight,
            "loss": args.loss_weight,
        },
        "criticality": {
            "teacher_semantics": "all legal children searched; child STM score negated to parent POV",
            "preserve_margin": args.preserve_margin,
            "unique_gap": args.unique_gap,
            "narrow_gap": args.narrow_gap,
            "narrow_ratio": args.narrow_ratio,
            "contested_ratio": args.contested_ratio,
            "multipliers": {
                "unique": args.unique_multiplier,
                "narrow": args.narrow_multiplier,
                "contested": args.contested_multiplier,
                "broad": 1.0,
                "forced_or_terminal": 1.0,
            },
            "weight_cap": args.weight_cap,
        },
        "profiled_parents": len(profile_by_index),
        "profile_bucket_counts": dict(bucket_counts),
        "profile_role_bucket_counts": {
            role: dict(counter) for role, counter in sorted(role_bucket_counts.items())
        },
        "criticality_multiplier_histogram": dict(multiplier_hist),
        "effective_weight_histogram": dict(effective_hist),
        "source_training_counts": {
            "win": source_code_counts[1], "draw": source_code_counts[0], "loss": source_code_counts[-1]
        },
        "resampled_training_counts": {
            "win": sampled_code_counts[1], "draw": sampled_code_counts[0], "loss": sampled_code_counts[-1]
        },
        "resampled_profile_bucket_counts": dict(sampled_bucket_counts),
        "seed": args.seed,
    }
    if args.profile_report:
        Path(args.profile_report).write_text(
            json.dumps({"schema": 1, "profiles": list(profile_by_index.values())}, indent=2, sort_keys=True) + "\n"
        )
    Path(args.report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    parents = sub.add_parser("make-parents", help="select and emit parent FENs to profile")
    parents.add_argument("--input", required=True)
    parents.add_argument("--holdout-count", type=int, required=True)
    parents.add_argument("--max-parents", type=int, default=25000,
                         help="0 profiles every eligible training parent")
    parents.add_argument("--tb-lock-pieces", type=int, default=6)
    parents.add_argument("--win-weight", type=float, default=1.0)
    parents.add_argument("--draw-weight", type=float, default=2.0)
    parents.add_argument("--loss-weight", type=float, default=4.0)
    parents.add_argument("--seed", type=int, required=True)
    parents.add_argument("--out-fen", required=True)
    parents.add_argument("--out-index", required=True)
    parents.set_defaults(func=cmd_make_parents)

    flatten = sub.add_parser("flatten-children", help="convert dump-children JSONL to aligned JNNW")
    flatten.add_argument("--parent-index", required=True)
    flatten.add_argument("--children-jsonl", required=True)
    flatten.add_argument("--out-data", required=True)
    flatten.add_argument("--out-index", required=True)
    flatten.set_defaults(func=cmd_flatten_children)

    merge = sub.add_parser("merge-jnnw", help="ordered merge of standalone JNNW shards")
    merge.add_argument("--input", action="append", required=True)
    merge.add_argument("--output", required=True)
    merge.add_argument("--report", required=True)
    merge.set_defaults(func=cmd_merge_jnnw)

    reweight = sub.add_parser("reweight", help="combine V1 outcome and move criticality weights")
    reweight.add_argument("--input", required=True)
    reweight.add_argument("--scored-children", required=True)
    reweight.add_argument("--child-index", required=True)
    reweight.add_argument("--output", required=True)
    reweight.add_argument("--holdout-count", type=int, required=True)
    reweight.add_argument("--win-weight", type=float, default=1.0)
    reweight.add_argument("--draw-weight", type=float, default=2.0)
    reweight.add_argument("--loss-weight", type=float, default=4.0)
    reweight.add_argument("--preserve-margin", type=int, default=50)
    reweight.add_argument("--unique-gap", type=int, default=75)
    reweight.add_argument("--narrow-gap", type=int, default=30)
    reweight.add_argument("--narrow-ratio", type=float, default=0.25)
    reweight.add_argument("--contested-ratio", type=float, default=0.50)
    reweight.add_argument("--unique-multiplier", type=float, default=3.0)
    reweight.add_argument("--narrow-multiplier", type=float, default=2.0)
    reweight.add_argument("--contested-multiplier", type=float, default=1.5)
    reweight.add_argument("--weight-cap", type=float, default=8.0)
    reweight.add_argument("--seed", type=int, required=True)
    reweight.add_argument("--report", required=True)
    reweight.add_argument("--profile-report")
    reweight.set_defaults(func=cmd_reweight)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
