#!/usr/bin/env python3
"""Aggregate the preregistered reverse-seed treatment-vs-control readout.

The force score is 1 for a treatment win, 1/2 for a draw and 0 for a control
win. Confidence intervals use the observed second moment of that score and a
large-sample normal approximation. The gate currently publishes aggregate
W/D/L only, so colour-pair clustering cannot be reconstructed afterwards and
is stated explicitly in the certificate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any


ABOVE_95 = "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95"
ABOVE_90 = "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC90"
DIRECTIONAL = "L3_PURE_REVERSE_SEED_DIRECTIONAL"
BELOW = "L3_PURE_REVERSE_SEED_BELOW_MATCHED_CONTROL"
INCONCLUSIVE = "L3_PURE_REVERSE_SEED_VS_MATCHED_CONTROL_INCONCLUSIVE"
SCALE4M_ABOVE_95 = "L3_PURE_REVERSE_SEED_SCALE4M_ABOVE_MATCHED_CONTROL_IC95"
SCALE4M_ABOVE_90 = "L3_PURE_REVERSE_SEED_SCALE4M_ABOVE_MATCHED_CONTROL_IC90"
SCALE4M_DIRECTIONAL = "L3_PURE_REVERSE_SEED_SCALE4M_DIRECTIONAL"
SCALE4M_BELOW = "L3_PURE_REVERSE_SEED_SCALE4M_BELOW_MATCHED_CONTROL"
SCALE4M_INCONCLUSIVE = (
    "L3_PURE_REVERSE_SEED_SCALE4M_VS_MATCHED_CONTROL_INCONCLUSIVE"
)


def verdict_names(experiment_stage: str) -> dict[str, str]:
    if experiment_stage == "base2m":
        return {
            "above95": ABOVE_95,
            "above90": ABOVE_90,
            "directional": DIRECTIONAL,
            "below": BELOW,
            "inconclusive": INCONCLUSIVE,
        }
    if experiment_stage == "scale4m":
        return {
            "above95": SCALE4M_ABOVE_95,
            "above90": SCALE4M_ABOVE_90,
            "directional": SCALE4M_DIRECTIONAL,
            "below": SCALE4M_BELOW,
            "inconclusive": SCALE4M_INCONCLUSIVE,
        }
    raise ValueError(f"unsupported experiment stage: {experiment_stage}")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _elo(rate: float) -> float | None:
    if not 0.0 < rate < 1.0:
        return None
    return -400.0 * math.log10(1.0 / rate - 1.0)


def _score_interval(
    wins: int,
    draws: int,
    losses: int,
    confidence: float,
) -> tuple[float, float]:
    n = wins + draws + losses
    if n <= 1:
        raise ValueError("force cell needs at least two games")
    rate = (wins + 0.5 * draws) / n
    second = (wins + 0.25 * draws) / n
    sample_variance = max(0.0, (second - rate * rate) * n / (n - 1))
    se = math.sqrt(sample_variance / n)
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return max(0.0, rate - z * se), min(1.0, rate + z * se)


def summarize_counts(wins: int, draws: int, losses: int) -> dict[str, Any]:
    if min(wins, draws, losses) < 0:
        raise ValueError("negative W/D/L count")
    n = wins + draws + losses
    if n <= 1:
        raise ValueError("force cell is empty or too short")
    rate = (wins + 0.5 * draws) / n
    lo90, hi90 = _score_interval(wins, draws, losses, 0.90)
    lo95, hi95 = _score_interval(wins, draws, losses, 0.95)
    return {
        "wins_treatment": wins,
        "draws": draws,
        "wins_control": losses,
        "n": n,
        "rate_treatment": rate,
        "elo": _elo(rate),
        "ci90": [lo90, hi90],
        "ci95": [lo95, hi95],
        "elo_ci90": [_elo(lo90), _elo(hi90)],
        "elo_ci95": [_elo(lo95), _elo(hi95)],
        "confidence_method": (
            "normal_score_mean_observed_second_moment; "
            "paired-colour clustering not identifiable from aggregate WDL"
        ),
    }


def force_cell(path: Path, expected_games: int) -> dict[str, Any]:
    value = load(path)
    wins = int(value["wins_a"])
    draws = int(value["draws"])
    losses = int(value["wins_b"])
    if int(value["n"]) != wins + draws + losses:
        raise ValueError(f"{path}: force W/D/L accounting mismatch")
    if int(value["n"]) != expected_games:
        raise ValueError(
            f"{path}: expected exactly {expected_games} games, got {value['n']}"
        )
    result = summarize_counts(wins, draws, losses)
    result["raw_gate_report"] = value
    return result


def compact_coverage(value: dict[str, Any]) -> dict[str, Any]:
    required = (
        "visited_buckets",
        "visited_pct",
        "gini",
        "buckets_ge_10",
        "buckets_ge_100",
    )
    if any(key not in value for key in required):
        raise ValueError("training coverage is incomplete")
    return {key: value[key] for key in required}


def _validate_training(
    training: dict[str, Any],
    source_code_sha: str,
    control_sha: str,
    treatment_sha: str,
    *,
    expected_verdict: str = "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
    expected_records_per_arm: int = 2_000_000,
    expected_experiment_stage: str = "base2m",
) -> None:
    design = training.get("design", {})
    if (
        training.get("verdict") != expected_verdict
        or training.get("code_sha") != source_code_sha
        or training.get("experiment_stage", "base2m")
        != expected_experiment_stage
        or training.get("primary_contrast")
        != "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY"
        or design.get("single_factor") != "seed_root_selection_policy"
        or design.get("records_per_arm") != expected_records_per_arm
        or design.get("seed_frac") != 100
        or design.get("historical_replay_records") != 0
        or design.get("same_parent") is not True
        or design.get("same_search_policy") is not True
        or design.get("same_shard_seeds") is not True
        or design.get("same_split_contract") is not True
        or design.get("same_fit") is not True
        or training.get("external_teacher_inputs") != 0
        or training.get("scientific_result") is not False
        or training.get("promotion_authorized") is not False
        or training.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError("reverse-seed training certificate mismatch")
    arms = training.get("arms", {})
    for arm, expected in (
        ("control", control_sha),
        ("treatment", treatment_sha),
    ):
        if (
            arms.get(arm, {}).get("model_sha256") != expected
            or arms.get(arm, {}).get("fit", {}).get("converged") is not True
        ):
            raise ValueError(f"{arm} model hash/convergence mismatch")
        compact_coverage(arms[arm].get("coverage", {}))


def build_readout(
    *,
    force_dir: Path,
    training_summary_path: Path,
    opening_manifest_path: Path,
    expected_games_per_view: int,
    expected_openings: int,
    code_sha: str,
    source_job: str,
    source_attempt: str,
    source_code_sha: str,
    expected_control_sha: str,
    expected_treatment_sha: str,
    experiment_stage: str = "base2m",
    expected_training_verdict: str = (
        "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY"
    ),
    expected_records_per_arm: int = 2_000_000,
) -> dict[str, Any]:
    training = load(training_summary_path)
    openings = load(opening_manifest_path)
    _validate_training(
        training,
        source_code_sha,
        expected_control_sha,
        expected_treatment_sha,
        expected_verdict=expected_training_verdict,
        expected_records_per_arm=expected_records_per_arm,
        expected_experiment_stage=experiment_stage,
    )
    if (
        openings.get("records") != expected_openings
        or openings.get("unique_records") != expected_openings
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        view: force_cell(
            force_dir / f"force-{view}-TREATMENT-vs-CONTROL.json",
            expected_games_per_view,
        )
        for view in ("q00", "native")
    }
    summed = summarize_counts(
        sum(force[view]["wins_treatment"] for view in force),
        sum(force[view]["draws"] for view in force),
        sum(force[view]["wins_control"] for view in force),
    )
    both_point_positive = all(
        force[view]["rate_treatment"] > 0.5 for view in force
    )
    any_view_regressed_90 = any(
        force[view]["ci90"][1] < 0.5 for view in force
    )
    names = verdict_names(experiment_stage)
    if both_point_positive and summed["ci95"][0] > 0.5:
        verdict = names["above95"]
    elif both_point_positive and summed["ci90"][0] > 0.5:
        verdict = names["above90"]
    elif summed["ci90"][1] < 0.5 or any_view_regressed_90:
        verdict = names["below"]
    elif summed["rate_treatment"] > 0.5 and not any_view_regressed_90:
        verdict = names["directional"]
    else:
        verdict = names["inconclusive"]

    control_cov = compact_coverage(training["arms"]["control"]["coverage"])
    treatment_cov = compact_coverage(training["arms"]["treatment"]["coverage"])
    coverage_delta = {
        key: treatment_cov[key] - control_cov[key]
        for key in (
            "visited_buckets",
            "visited_pct",
            "gini",
            "buckets_ge_10",
            "buckets_ge_100",
        )
    }
    return {
        "schema": 1,
        "verdict": verdict,
        "code_sha": code_sha,
        "experiment_stage": experiment_stage,
        "source": {
            "job_id": source_job,
            "attempt_id": source_attempt,
            "code_sha": source_code_sha,
        },
        "models": {
            "control_sha256": expected_control_sha,
            "treatment_sha256": expected_treatment_sha,
        },
        "protocol": {
            "primary_contrast": (
                "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY"
            ),
            "single_training_factor": "seed_root_selection_policy",
            "records_per_arm": expected_records_per_arm,
            "paired_colours": True,
            "fresh_disjoint_openings": True,
            "openings": expected_openings,
            "games_per_view": expected_games_per_view,
            "views": ["q00_depth9", "native_movetime_0.1"],
            "holdout_is_diagnostic_only": True,
            "holdout_not_used_for_selection": True,
        },
        "opening_manifest": openings,
        "force": force,
        "force_views_summed": summed,
        "training_coverage": {
            "control": control_cov,
            "treatment": treatment_cov,
            "treatment_minus_control": coverage_delta,
        },
        "decision_evidence": {
            "both_force_views_point_positive": both_point_positive,
            "summed_force_superiority_90": summed["ci90"][0] > 0.5,
            "summed_force_superiority_95": summed["ci95"][0] > 0.5,
            "any_force_view_regressed_90": any_view_regressed_90,
        },
        "scientific_result": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-games-per-view", required=True, type=int)
    parser.add_argument("--expected-openings", required=True, type=int)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--control-model-sha", required=True)
    parser.add_argument("--treatment-model-sha", required=True)
    parser.add_argument(
        "--experiment-stage",
        choices=("base2m", "scale4m"),
        default="base2m",
    )
    parser.add_argument(
        "--expected-training-verdict",
        default="L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
    )
    parser.add_argument(
        "--expected-records-per-arm",
        type=int,
        default=2_000_000,
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args(argv)
    payload = build_readout(
        force_dir=args.force_dir,
        training_summary_path=args.training_summary,
        opening_manifest_path=args.opening_manifest,
        expected_games_per_view=args.expected_games_per_view,
        expected_openings=args.expected_openings,
        code_sha=args.code_sha,
        source_job=args.source_job,
        source_attempt=args.source_attempt,
        source_code_sha=args.source_code_sha,
        expected_control_sha=args.control_model_sha,
        expected_treatment_sha=args.treatment_model_sha,
        experiment_stage=args.experiment_stage,
        expected_training_verdict=args.expected_training_verdict,
        expected_records_per_arm=args.expected_records_per_arm,
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
