#!/usr/bin/env python3
"""Aggregate the independent high-N confirmation of L3 temporal turnover."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


CHAMPION_REVIEW = "TURNOVER_CHAMPION_CONFIRMATION_REVIEW_READY"
EFFECT_CONFIRMED = "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
DIRECTION_REPLICATED = "TURNOVER_DIRECTION_REPLICATED_REVIEW"
NOT_REPLICATED = "TURNOVER_DIRECTION_NOT_REPLICATED_CLOSE_1TO1"

PREVIOUS_VERDICT = "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
PREVIOUS_RECOMMENDATION = "independent_turnover_confirmation"
TURNOVER_CODE_SHA = "336bb98451a205266d6646c4d801027af4b30294"
TURNOVER_MODEL_SHA = (
    "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
)
TURNOVER_CORPUS_SHA = (
    "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
)
TURNOVER_META_SHA = (
    "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
)
PREVIOUS_OPENING_SEED = 732_051
PREVIOUS_OPENING_SHA = (
    "6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d"
)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def summarize_counts(wins: int, draws: int, losses: int) -> dict[str, Any]:
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("force report contains zero games")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    ci_low = max(0.0, rate - 1.96 * se)
    ci_high = min(1.0, rate + 1.96 * se)
    elo = -400 * math.log10(1 / rate - 1) if 0 < rate < 1 else 0.0
    return {
        "wins_a": wins,
        "draws": draws,
        "wins_b": losses,
        "n": n,
        "rate": round(rate, 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "elo": round(elo, 2),
    }


def validate_force_row(
    value: dict[str, Any],
    *,
    expected_n: int,
    label: str,
    require_complete: bool,
) -> dict[str, Any]:
    try:
        wins = int(value["wins_a"])
        draws = int(value["draws"])
        losses = int(value["wins_b"])
        reported_n = int(value["n"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label}: malformed force counts") from exc
    if min(wins, draws, losses) < 0 or reported_n != expected_n:
        raise ValueError(f"{label}: force size/count mismatch")
    if require_complete and value.get("complete") is not True:
        raise ValueError(f"{label}: incomplete force report")
    expected = summarize_counts(wins, draws, losses)
    if expected["n"] != reported_n:
        raise ValueError(f"{label}: W/D/L do not sum to n")
    for key in ("rate", "ci_low", "ci_high"):
        if abs(float(value[key]) - float(expected[key])) > 1e-6:
            raise ValueError(f"{label}: derived {key} mismatch")
    if abs(float(value["elo"]) - float(expected["elo"])) > 0.011:
        raise ValueError(f"{label}: derived elo mismatch")
    return expected


def combine_rows(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    combined = summarize_counts(
        int(first["wins_a"]) + int(second["wins_a"]),
        int(first["draws"]) + int(second["draws"]),
        int(first["wins_b"]) + int(second["wins_b"]),
    )
    combined.update(
        {
            "independent_opening_pools": True,
            "source_games": [int(first["n"]), int(second["n"])],
        }
    )
    return combined


def checks(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "positive_point_estimate": float(row["rate"]) > 0.5,
        "superiority_established": float(row["ci_low"]) > 0.5,
        "regression_not_established": float(row["ci_high"]) >= 0.5,
    }


def validate_previous(previous: dict[str, Any]) -> dict[str, dict[str, Any]]:
    training = previous.get("training_summary", {})
    openings = previous.get("opening_manifest", {})
    if (
        previous.get("verdict") != PREVIOUS_VERDICT
        or previous.get("recommendation") != PREVIOUS_RECOMMENDATION
        or previous.get("all_guardrails_pass") is not True
        or previous.get("promotion_authorized") is not False
        or previous.get("automatic_next_job") is not None
        or not previous.get("guardrails")
        or not all(previous["guardrails"].values())
    ):
        raise ValueError("previous turnover evaluation certificate mismatch")
    if (
        training.get("code_sha") != TURNOVER_CODE_SHA
        or training.get("model_sha256") != TURNOVER_MODEL_SHA
        or training.get("training_corpus_sha256") != TURNOVER_CORPUS_SHA
        or training.get("training_meta_sha256") != TURNOVER_META_SHA
        or training.get("experiment_variant") != "TURNOVER_1_1"
        or training.get("parent") != "F2M"
        or training.get("fresh_only") is not False
        or training.get("training_records") != 2_000_000
        or training.get("historical_replay_records") != 1_000_000
        or training.get("fresh_records") != 1_000_000
        or training.get("temporal_distribution_records")
        != {"fresh_m2": 1_000_000, "parent_f2m": 1_000_000}
        or training.get("new_generation_performed") is not False
    ):
        raise ValueError("previous turnover model/training identity mismatch")
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != PREVIOUS_OPENING_SEED
        or openings.get("sha256") != PREVIOUS_OPENING_SHA
    ):
        raise ValueError("previous turnover opening-pool identity mismatch")

    force: dict[str, dict[str, Any]] = {}
    primary = previous.get("primary_checks", {})
    for control in ("M2", "F2M"):
        for view in ("q00", "native"):
            key = f"{view}_vs_{control}"
            force[key] = validate_force_row(
                previous.get("force", {}).get(key, {}),
                expected_n=1_000,
                label=f"previous {key}",
                require_complete=False,
            )
            if primary.get(control, {}).get(view) != {
                "positive_point_estimate": True,
                "superiority_established": False,
                "regression_not_established": True,
            }:
                raise ValueError("previous directional force certificate mismatch")
    return force


def validate_openings(
    openings: dict[str, Any],
    *,
    expected_seed: int,
    expected_sha256: str,
    expected_candidate_sha256: str,
) -> None:
    excluded = openings.get("excluded_sources", {})
    required_suffixes = (
        "prior-m2-independent.fen",
        "prior-d10-independent.fen",
        "prior-d12-independent.fen",
        "prior-turnover-independent.fen",
    )
    if (
        openings.get("records") != 1_000
        or openings.get("unique_records") != 1_000
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != expected_seed
        or openings.get("sha256") != expected_sha256
        or openings.get("candidate_sha256") != expected_candidate_sha256
        or not all(
            any(str(path).endswith(suffix) for path in excluded)
            for suffix in required_suffixes
        )
    ):
        raise ValueError("confirmation independent opening-pool contract mismatch")


def build_confirmation(
    *,
    force_dir: Path,
    previous_evaluation_path: Path,
    opening_manifest_path: Path,
    expected_opening_seed: int,
    expected_opening_sha256: str,
    expected_candidate_sha256: str,
) -> dict[str, Any]:
    previous = load(previous_evaluation_path)
    previous_force = validate_previous(previous)
    openings = load(opening_manifest_path)
    validate_openings(
        openings,
        expected_seed=expected_opening_seed,
        expected_sha256=expected_opening_sha256,
        expected_candidate_sha256=expected_candidate_sha256,
    )

    fresh: dict[str, dict[str, Any]] = {}
    pooled: dict[str, dict[str, Any]] = {}
    fresh_checks: dict[str, dict[str, dict[str, bool]]] = {
        "M2": {},
        "F2M": {},
    }
    pooled_checks: dict[str, dict[str, dict[str, bool]]] = {
        "M2": {},
        "F2M": {},
    }
    for control in ("M2", "F2M"):
        for view in ("q00", "native"):
            key = f"{view}_vs_{control}"
            fresh[key] = validate_force_row(
                load(force_dir / f"force-{view}-TURNOVER-vs-{control}.json"),
                expected_n=2_000,
                label=f"fresh {key}",
                require_complete=True,
            )
            pooled[key] = combine_rows(previous_force[key], fresh[key])
            fresh_checks[control][view] = checks(fresh[key])
            pooled_checks[control][view] = checks(pooled[key])

    carried_guardrails = {
        "source_static_guardrails_all_pass": previous["all_guardrails_pass"] is True,
        "source_model_identity_unchanged": (
            previous["training_summary"]["model_sha256"] == TURNOVER_MODEL_SHA
        ),
        "fresh_pool_independent": openings["overlap_records"] == 0,
    }
    for view in ("q00", "native"):
        carried_guardrails[f"fresh_f2m_{view}_regression_not_established"] = (
            fresh_checks["F2M"][view]["regression_not_established"]
        )
        carried_guardrails[f"pooled_f2m_{view}_regression_not_established"] = (
            pooled_checks["F2M"][view]["regression_not_established"]
        )
    all_guardrails = all(carried_guardrails.values())

    fresh_positive_m2 = all(
        fresh_checks["M2"][view]["positive_point_estimate"]
        for view in ("q00", "native")
    )
    fresh_positive_all = fresh_positive_m2 and all(
        fresh_checks["F2M"][view]["positive_point_estimate"]
        for view in ("q00", "native")
    )
    pooled_m2_superior = all(
        pooled_checks["M2"][view]["superiority_established"]
        for view in ("q00", "native")
    )
    pooled_all_superior = pooled_m2_superior and all(
        pooled_checks["F2M"][view]["superiority_established"]
        for view in ("q00", "native")
    )
    f2m_not_regressive = all(
        fresh_checks["F2M"][view]["regression_not_established"]
        and pooled_checks["F2M"][view]["regression_not_established"]
        for view in ("q00", "native")
    )

    if fresh_positive_all and pooled_all_superior and all_guardrails:
        verdict = CHAMPION_REVIEW
        recommendation = "human_review_turnover_as_l3_champion_candidate"
    elif (
        fresh_positive_m2
        and pooled_m2_superior
        and f2m_not_regressive
        and all_guardrails
    ):
        verdict = EFFECT_CONFIRMED
        recommendation = "human_review_temporal_turnover_effect_and_next_scale"
    elif fresh_positive_m2 and f2m_not_regressive and all_guardrails:
        verdict = DIRECTION_REPLICATED
        recommendation = "retain_turnover_signal_for_human_scale_decision"
    else:
        verdict = NOT_REPLICATED
        recommendation = "close_turnover_1to1_and_preregister_next_single_factor"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "TURNOVER_1_1",
            "causal_control": "M2_D8_FRESH2M",
            "champion": "F2M",
            "confirmation_openings": 1_000,
            "confirmation_games_per_cell": 2_000,
            "previous_games_per_cell": 1_000,
            "pooled_games_per_cell": 3_000,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "same_immutable_model": True,
            "rerun_static_guardrails": False,
            "changed_factor": "independent_evaluation_sample_only",
        },
        "fresh_force": fresh,
        "pooled_force": pooled,
        "fresh_checks": fresh_checks,
        "pooled_checks": pooled_checks,
        "guardrails": carried_guardrails,
        "all_guardrails_pass": all_guardrails,
        "previous_evaluation_certificate": {
            "verdict": previous["verdict"],
            "recommendation": previous["recommendation"],
            "model_sha256": previous["training_summary"]["model_sha256"],
            "training_corpus_sha256": previous["training_summary"][
                "training_corpus_sha256"
            ],
            "training_meta_sha256": previous["training_summary"][
                "training_meta_sha256"
            ],
            "opening_manifest": previous["opening_manifest"],
            "force": previous_force,
            "guardrails": previous["guardrails"],
            "all_guardrails_pass": previous["all_guardrails_pass"],
        },
        "opening_manifest": openings,
        "recommendation": recommendation,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--previous-evaluation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-opening-seed", required=True, type=int)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_confirmation(
        force_dir=args.force_dir,
        previous_evaluation_path=args.previous_evaluation,
        opening_manifest_path=args.opening_manifest,
        expected_opening_seed=args.expected_opening_seed,
        expected_opening_sha256=args.expected_opening_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
    )
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
