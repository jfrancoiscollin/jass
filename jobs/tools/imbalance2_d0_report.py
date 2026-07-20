#!/usr/bin/env python3
"""Aggregate D0 multi-depth traces into explicit, non-promotable hypotheses.

The classifications are diagnostic heuristics, not causal proof.  They route a
future *single-factor* pilot toward search, representation/objective, or
training-credit/distribution.  D1 remains forbidden until human review.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Iterable

ENGINES = ("g4", "g8", "scan")
DEPTHS = (8, 10, 12, 14)


def load_replays(paths: Iterable[str]) -> dict[tuple[str, str, int], dict[str, object]]:
    rows: dict[tuple[str, str, int], dict[str, object]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("protocol") != "imbalance2-d0-static-multidepth-replay":
            raise ValueError(f"{path}: unexpected replay protocol")
        if tuple(payload.get("depths", [])) != DEPTHS or payload.get("scan_bb_size") != 0:
            raise ValueError(f"{path}: replay contract mismatch")
        for row in payload.get("rows", []):
            key = (str(row["sentinel_id"]), str(row["engine"]), int(row["requested_depth"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate replay key {key}")
            if "error" in row:
                raise ValueError(f"{path}: engine error at {key}: {row['error']}")
            analysis = row.get("analysis")
            if not isinstance(analysis, dict) or not analysis.get("best_move"):
                raise ValueError(f"{path}: incomplete analysis at {key}")
            rows[key] = row
    return rows


def material_up_score(sentinel: dict[str, object], analysis: dict[str, object]) -> int | None:
    score = analysis.get("score")
    if score is None:
        return None
    stm = str(sentinel["fen"])[0]
    advantaged = str(sentinel["advantaged_side"])
    return int(score) if stm == advantaged else -int(score)


def first_match_depth(moves: dict[int, str], anchor: str) -> int | None:
    for depth in DEPTHS:
        if moves[depth] == anchor:
            return depth
    return None


def classify(
    sentinel: dict[str, object],
    traces: dict[str, dict[int, dict[str, object]]],
) -> tuple[str, list[str]]:
    g4_moves = {depth: str(traces["g4"][depth]["best_move"]) for depth in DEPTHS}
    g8_moves = {depth: str(traces["g8"][depth]["best_move"]) for depth in DEPTHS}
    scan_anchor = str(traces["scan"][14]["best_move"])
    reasons: list[str] = []

    late_g8 = first_match_depth(g8_moves, scan_anchor)
    if late_g8 in (12, 14) and g8_moves[8] != scan_anchor and g8_moves[10] != scan_anchor:
        reasons.append(f"G8 converge vers le coup Scan d14 seulement a d{late_g8}")
        return "SEARCH_HORIZON_CANDIDATE", reasons

    g4_stable = len(set(g4_moves.values())) == 1
    g8_stable = len(set(g8_moves.values())) == 1
    if g4_stable and g8_stable and g4_moves[14] != scan_anchor and g8_moves[14] != scan_anchor:
        reasons.append("G4 et G8 restent stables d8-d14 mais divergent du coup Scan d14")
        return "REPRESENTATION_OR_OBJECTIVE_CANDIDATE", reasons

    if g4_moves[14] == scan_anchor and g8_moves[14] != scan_anchor:
        reasons.append("G4 rejoint Scan a d14 mais G8 s'en eloigne")
        return "TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE", reasons
    if (
        float(sentinel["g8_minus_g4_cost"]) > 0
        and g8_moves[14] != scan_anchor
        and late_g8 is None
    ):
        reasons.append("issue G8 plus couteuse que G4 et aucune convergence vers Scan jusqu'a d14")
        return "TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE", reasons

    reasons.append("signaux de profondeur, evaluation et apprentissage non separables sur ce cas")
    return "SEARCH_AND_EVAL_MIXED", reasons


def recommend(counts: Counter[str], total: int) -> str:
    shares = {name: counts[name] / total for name in counts}
    if shares.get("SEARCH_HORIZON_CANDIDATE", 0.0) >= 0.40:
        return "PRIORITIZE_SEARCH_MECHANISM_PILOT"
    if shares.get("REPRESENTATION_OR_OBJECTIVE_CANDIDATE", 0.0) >= 0.40:
        return "PRIORITIZE_CONVERSION_FEATURE_PILOT"
    if shares.get("TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE", 0.0) >= 0.30:
        return "PRIORITIZE_TARGET_OR_SAMPLING_PILOT"
    return "MIXED_CAUSES_REQUIRE_SEPARATE_PILOTS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", required=True)
    parser.add_argument("--replay-inputs", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    sentinel_payload = json.loads(Path(args.sentinels).read_text(encoding="utf-8"))
    if sentinel_payload.get("protocol") != "imbalance2-d0-causal-sentinel-selection":
        parser.error("unexpected sentinel protocol")
    sentinels = sentinel_payload.get("sentinels", [])
    if not 20 <= len(sentinels) <= 40:
        parser.error("D0 requires 20..40 sentinels")
    replay = load_replays(args.replay_inputs)
    expected = {
        (str(item["sentinel_id"]), engine, depth)
        for item in sentinels for engine in ENGINES for depth in DEPTHS
    }
    if set(replay) != expected:
        missing = sorted(expected - set(replay))[:10]
        extra = sorted(set(replay) - expected)[:10]
        parser.error(f"replay matrix incomplete; missing={missing} extra={extra}")

    cases: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
    for sentinel in sentinels:
        sentinel_id = str(sentinel["sentinel_id"])
        traces: dict[str, dict[int, dict[str, object]]] = {
            engine: {
                depth: dict(replay[(sentinel_id, engine, depth)]["analysis"])
                for depth in DEPTHS
            }
            for engine in ENGINES
        }
        hypothesis, reasons = classify(sentinel, traces)
        counts[hypothesis] += 1
        by_stratum[str(sentinel["stratum"])][hypothesis] += 1
        scan_anchor = str(traces["scan"][14]["best_move"])
        case = dict(sentinel)
        case.update({
            "causal_hypothesis": hypothesis,
            "hypothesis_is_proof": False,
            "reasons": reasons,
            "scan_d14_anchor_move": scan_anchor,
            "g4_first_match_scan_d14": first_match_depth(
                {depth: str(traces["g4"][depth]["best_move"]) for depth in DEPTHS}, scan_anchor
            ),
            "g8_first_match_scan_d14": first_match_depth(
                {depth: str(traces["g8"][depth]["best_move"]) for depth in DEPTHS}, scan_anchor
            ),
            "g4_material_up_scores": {
                str(depth): material_up_score(sentinel, traces["g4"][depth]) for depth in DEPTHS
            },
            "g8_material_up_scores": {
                str(depth): material_up_score(sentinel, traces["g8"][depth]) for depth in DEPTHS
            },
            "traces": traces,
        })
        cases.append(case)

    recommendation = recommend(counts, len(cases))
    output = {
        "schema": 1,
        "protocol": "imbalance2-d0-causal-diagnostic",
        "lineage": "L3-IMBALANCE2-ROLE-V2",
        "sentinel_count": len(cases),
        "searches": len(cases) * len(ENGINES) * len(DEPTHS),
        "selfplay_games": 0,
        "training_records": 0,
        "depths": list(DEPTHS),
        "engines": list(ENGINES),
        "classification_is_hypothesis_not_proof": True,
        "hypothesis_counts": dict(sorted(counts.items())),
        "hypothesis_shares": {
            name: value / len(cases) for name, value in sorted(counts.items())
        },
        "strata": {
            stratum: dict(sorted(values.items()))
            for stratum, values in sorted(by_stratum.items(), key=lambda item: int(item[0].split("v", 1)[0]))
        },
        "recommendation_for_human_review": recommendation,
        "cases": cases,
        "decision": "D0_CAUSAL_PROFILE_READY",
        "d1_authorized": False,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"D0_CAUSAL_PROFILE_READY recommendation={recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
