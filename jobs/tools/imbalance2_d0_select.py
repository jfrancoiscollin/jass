#!/usr/bin/env python3
"""Select a bounded, auditable D0 sentinel set from the completed G4/G8 campaign.

The selector consumes symmetrically cleaned candidate-only A64/B64 reports, the
immutable pool bytes/metadata, and the raw material-difficulty reference.  It
chooses unique positions from three causal families:

* G4->G8 regressions;
* persistent distance to exact EGDB or the empirical Scan reference;
* strata with the strongest A/B divergence.

The reference is descriptive only.  This tool never creates training data,
weights, labels, models, or a promotion decision.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import glob
import json
from pathlib import Path
import struct
from typing import Iterable

MAGIC = b"JNNW"
REC_SIZE = 38
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}
EXPECTED_POOLS = {"plateau-a.jnnw", "plateau-b.jnnw"}
EXPECTED_STRATA = {f"{n}v{n + 2}" for n in range(1, 19)}


def read_jnnw(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC_SIZE:
        raise ValueError(f"{path}: size/count mismatch")
    return [body[i * REC_SIZE:(i + 1) * REC_SIZE] for i in range(count)]


def record_to_fen(record: bytes) -> str:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = int(record[32])
    if stm not in (0, 1):
        raise ValueError("invalid side-to-move byte")

    def pieces(men: int, kings: int) -> str:
        values = [str(square) for square in range(1, 51) if men & (1 << (square - 1))]
        values.extend(f"K{square}" for square in range(1, 51) if kings & (1 << (square - 1)))
        return ",".join(values)

    return f"{'B' if stm else 'W'}:W{pieces(wm, wk)}:B{pieces(bm, bk)}"


def up_outcome_from_tb(record: bytes, item: dict[str, object]) -> str:
    stm = int(record[32])
    wdl = struct.unpack_from("<b", record, 37)[0]
    if stm not in (0, 1) or wdl not in (-1, 0, 1):
        raise ValueError("invalid exact-TB STM/WDL record")
    advantaged = str(item["advantaged_side"])
    if advantaged not in ("W", "B"):
        raise ValueError("invalid advantaged side")
    up_is_stm = (advantaged == "W" and stm == 0) or (advantaged == "B" and stm == 1)
    value = wdl if up_is_stm else -wdl
    return {1: "win", 0: "draw", -1: "loss"}[value]


def load_candidate(paths: Iterable[str]) -> dict[tuple[str, int], dict[str, object]]:
    rows: dict[tuple[str, int], dict[str, object]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("engine") != "candidate":
            raise ValueError(f"{path}: expected candidate report")
        pool = Path(str(payload.get("pool", ""))).name
        if pool not in EXPECTED_POOLS:
            raise ValueError(f"{path}: unexpected pool {pool!r}")
        for row in payload.get("rows", []):
            if "error" in row:
                raise ValueError(f"{path}: reports must be symmetrically cleaned")
            key = (pool, int(row["index"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate key {key}")
            outcome = str(row.get("outcome"))
            stratum = str(row.get("stratum"))
            if outcome not in COST or stratum not in EXPECTED_STRATA:
                raise ValueError(f"{path}: invalid row at {key}")
            rows[key] = {"outcome": outcome, "stratum": stratum}
    return rows


def load_pool(path: Path, meta_path: Path) -> dict[tuple[str, int], dict[str, object]]:
    records = read_jnnw(path)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if len(records) != len(metadata):
        raise ValueError(f"{path}: pool/meta length mismatch")
    pool = path.name
    if pool not in EXPECTED_POOLS:
        raise ValueError(f"unexpected pool basename {pool!r}")
    result: dict[tuple[str, int], dict[str, object]] = {}
    for index, (record, raw_item) in enumerate(zip(records, metadata, strict=True)):
        item = dict(raw_item)
        stratum = str(item.get("stratum"))
        if stratum not in EXPECTED_STRATA:
            raise ValueError(f"{path}: invalid stratum at index {index}")
        item.update({"fen": record_to_fen(record), "pool": pool, "index": index})
        result[(pool, index)] = item
    return result


def load_reference(root: Path) -> dict[tuple[str, int], dict[str, object]]:
    reference: dict[tuple[str, int], dict[str, object]] = {}
    for label in ("a", "b"):
        exact_data = root / f"exact-{label}/plateau-{label}-labelled.jnnw"
        exact_meta_path = root / f"exact-{label}/plateau-{label}.json"
        records = read_jnnw(exact_data)
        metadata = json.loads(exact_meta_path.read_text(encoding="utf-8"))
        if len(records) != len(metadata):
            raise ValueError(f"{exact_data}: exact data/meta mismatch")
        for record, item in zip(records, metadata, strict=True):
            key = (Path(str(item["source_pool"])).name, int(item["source_index"]))
            reference[key] = {
                "outcome": up_outcome_from_tb(record, item),
                "source": "exact_egdb_wdl",
                "reference_is_exact": True,
            }

        high_meta_path = root / f"high-{label}/plateau-{label}.json"
        high_meta = json.loads(high_meta_path.read_text(encoding="utf-8"))
        seen_local: set[int] = set()
        for raw_path in sorted(glob.glob(str(root / f"scan-{label}/plateau-{label}.s*.json"))):
            path = Path(raw_path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("engine") != "scan":
                raise ValueError(f"{path}: expected Scan report")
            for row in payload.get("rows", []):
                if "error" in row:
                    raise ValueError(f"{path}: Scan reference contains an error")
                local_index = int(row["index"])
                if local_index in seen_local:
                    raise ValueError(f"{path}: duplicate Scan local index {local_index}")
                seen_local.add(local_index)
                item = high_meta[local_index]
                key = (Path(str(item["source_pool"])).name, int(item["source_index"]))
                reference[key] = {
                    "outcome": str(row["outcome"]),
                    "source": "scan_d10_selfplay_reference",
                    "reference_is_exact": False,
                }
        if len(seen_local) != len(high_meta):
            raise ValueError(f"pool {label}: incomplete Scan reference coverage")
    return reference


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("empty mean")
    return sum(values) / len(values)


def rank_sentinels(
    rows: list[dict[str, object]],
    *,
    per_family: int,
    max_total: int,
    min_total: int = 20,
) -> list[dict[str, object]]:
    if per_family <= 0 or not 20 <= max_total <= 40 or min_total > max_total:
        raise ValueError("invalid sentinel bounds")

    families: list[tuple[str, list[dict[str, object]]]] = [
        (
            "g4_to_g8_regression",
            sorted(
                rows,
                key=lambda row: (
                    float(row["g8_minus_g4_cost"]),
                    float(row["g8_minus_reference_cost"]),
                    float(row["stratum_ab_divergence"]),
                ),
                reverse=True,
            ),
        ),
        (
            "persistent_reference_gap",
            sorted(
                rows,
                key=lambda row: (
                    min(float(row["g4_minus_reference_cost"]), float(row["g8_minus_reference_cost"])),
                    float(row["g8_minus_reference_cost"]),
                    float(row["g8_minus_g4_cost"]),
                ),
                reverse=True,
            ),
        ),
        (
            "pool_divergence",
            sorted(
                rows,
                key=lambda row: (
                    float(row["stratum_ab_divergence"]),
                    abs(float(row["g8_minus_g4_cost"])),
                    float(row["g8_minus_reference_cost"]),
                ),
                reverse=True,
            ),
        ),
    ]

    selected: list[dict[str, object]] = []
    used: set[tuple[str, int]] = set()
    for family, candidates in families:
        taken = 0
        for candidate in candidates:
            key = (str(candidate["pool"]), int(candidate["index"]))
            if key in used:
                continue
            if family == "g4_to_g8_regression" and float(candidate["g8_minus_g4_cost"]) <= 0:
                continue
            if family == "persistent_reference_gap" and not (
                float(candidate["g4_minus_reference_cost"]) > 0
                and float(candidate["g8_minus_reference_cost"]) > 0
            ):
                continue
            item = dict(candidate)
            item["family"] = family
            item["family_rank"] = taken + 1
            selected.append(item)
            used.add(key)
            taken += 1
            if taken >= per_family or len(selected) >= max_total:
                break

    if len(selected) < max_total:
        backfill = sorted(
            rows,
            key=lambda row: (
                max(0.0, float(row["g8_minus_g4_cost"])) * 3.0
                + max(0.0, float(row["g8_minus_reference_cost"])) * 2.0
                + float(row["stratum_ab_divergence"])
            ),
            reverse=True,
        )
        for candidate in backfill:
            key = (str(candidate["pool"]), int(candidate["index"]))
            if key in used:
                continue
            item = dict(candidate)
            item["family"] = "hard_case_backfill"
            item["family_rank"] = 1 + sum(
                other["family"] == "hard_case_backfill" for other in selected
            )
            selected.append(item)
            used.add(key)
            if len(selected) >= max_total:
                break

    if not min_total <= len(selected) <= 40:
        raise ValueError(f"sentinel set has {len(selected)} positions; expected {min_total}..40")
    for ordinal, item in enumerate(selected, 1):
        item["sentinel_id"] = f"D0-{ordinal:02d}"
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pool-a-data", required=True)
    parser.add_argument("--pool-a-meta", required=True)
    parser.add_argument("--pool-b-data", required=True)
    parser.add_argument("--pool-b-meta", required=True)
    parser.add_argument("--reference-raw", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--per-family", type=int, default=10)
    parser.add_argument("--max-total", type=int, default=30)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_pools") is not True or manifest.get("same_search_budget") is not True:
        parser.error("D0 requires identical pools and search budgets")
    report_sets = manifest.get("report_sets", {})
    if not {"G4", "G8"}.issubset(report_sets):
        parser.error("clean manifest must contain G4 and G8")
    g4 = load_candidate(report_sets["G4"])
    g8 = load_candidate(report_sets["G8"])
    if set(g4) != set(g8):
        parser.error("G4/G8 keys differ after symmetric cleaning")

    pool_positions = {}
    pool_positions.update(load_pool(Path(args.pool_a_data), Path(args.pool_a_meta)))
    pool_positions.update(load_pool(Path(args.pool_b_data), Path(args.pool_b_meta)))
    reference = load_reference(Path(args.reference_raw))
    if not set(g4).issubset(pool_positions) or not set(g4).issubset(reference):
        parser.error("pool or reference does not cover every cleaned G4/G8 key")

    deltas: dict[tuple[str, str], list[float]] = defaultdict(list)
    for key in sorted(g4):
        deltas[(key[0], str(g4[key]["stratum"]))].append(
            COST[str(g8[key]["outcome"])] - COST[str(g4[key]["outcome"])]
        )
    divergence: dict[str, float] = {}
    for stratum in EXPECTED_STRATA:
        a = mean(deltas[("plateau-a.jnnw", stratum)])
        b = mean(deltas[("plateau-b.jnnw", stratum)])
        divergence[stratum] = abs(a - b)

    rows: list[dict[str, object]] = []
    for key in sorted(g4):
        pool, index = key
        item = pool_positions[key]
        ref = reference[key]
        g4_outcome = str(g4[key]["outcome"])
        g8_outcome = str(g8[key]["outcome"])
        ref_outcome = str(ref["outcome"])
        stratum = str(g4[key]["stratum"])
        rows.append({
            "pool": pool,
            "index": index,
            "stratum": stratum,
            "total_pieces": int(item["white_men"]) + int(item["black_men"]),
            "advantaged_side": str(item["advantaged_side"]),
            "fen": str(item["fen"]),
            "g4_outcome": g4_outcome,
            "g8_outcome": g8_outcome,
            "reference_outcome": ref_outcome,
            "reference_source": str(ref["source"]),
            "reference_is_exact": bool(ref["reference_is_exact"]),
            "g8_minus_g4_cost": COST[g8_outcome] - COST[g4_outcome],
            "g4_minus_reference_cost": COST[g4_outcome] - COST[ref_outcome],
            "g8_minus_reference_cost": COST[g8_outcome] - COST[ref_outcome],
            "stratum_ab_divergence": divergence[stratum],
        })

    sentinels = rank_sentinels(
        rows,
        per_family=args.per_family,
        max_total=args.max_total,
    )
    payload = {
        "schema": 1,
        "protocol": "imbalance2-d0-causal-sentinel-selection",
        "lineage": "L3-IMBALANCE2-ROLE-V2",
        "baseline_generation": "G4",
        "treatment_generation": "G8",
        "same_pools": True,
        "same_search_budget_for_outcome_reports": True,
        "reference_used_for_selection_only": True,
        "reference_used_for_training": False,
        "reference_used_for_weighting": False,
        "selection_is_diagnostic_only": True,
        "sentinel_count": len(sentinels),
        "family_counts": dict(sorted(Counter(str(item["family"]) for item in sentinels).items())),
        "sentinels": sentinels,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"D0_SENTINELS_READY n={len(sentinels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
