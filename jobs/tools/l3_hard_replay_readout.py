#!/usr/bin/env python3
"""Aggregate the preregistered HARD_REPLAY-vs-UNIFORM_REPLAY readout.

Force confidence intervals use the observed second moment of the W/D/L score
(1, 1/2, 0) and the large-sample normal approximation.  Conversion deltas are
paired by immutable source index and use the exact distribution of an
empirical trinomial bootstrap, so no random Monte-Carlo error is introduced.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any


ABOVE_95 = "L3_PURE_HARD_REPLAY_ABOVE_UNIFORM_REPLAY_IC95"
ABOVE_90 = "L3_PURE_HARD_REPLAY_ABOVE_UNIFORM_REPLAY_IC90"
DIRECTIONAL = "L3_PURE_HARD_REPLAY_DIRECTIONAL"
BELOW = "L3_PURE_HARD_REPLAY_BELOW_UNIFORM_REPLAY"
INCONCLUSIVE = "L3_PURE_HARD_REPLAY_VS_UNIFORM_REPLAY_INCONCLUSIVE"


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
    # Unbiased variance of individual game scores, followed by the standard
    # error of their mean.
    sample_variance = max(0.0, (second - rate * rate) * n / (n - 1))
    se = math.sqrt(sample_variance / n)
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    return max(0.0, rate - z * se), min(1.0, rate + z * se)


def summarize_force_counts(wins: int, draws: int, losses: int) -> dict[str, Any]:
    if min(wins, draws, losses) < 0:
        raise ValueError("negative W/D/L count")
    n = wins + draws + losses
    if n <= 1:
        raise ValueError("force cell is empty or too short")
    rate = (wins + 0.5 * draws) / n
    lo90, hi90 = _score_interval(wins, draws, losses, 0.90)
    lo95, hi95 = _score_interval(wins, draws, losses, 0.95)
    return {
        "wins_hard_replay": wins,
        "draws": draws,
        "wins_uniform_replay": losses,
        "n": n,
        "rate_hard_replay": rate,
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
    result = summarize_force_counts(wins, draws, losses)
    result["raw_gate_report"] = value
    return result


def _position_wins(report: dict[str, Any]) -> dict[int, int]:
    if report.get("complete") is not True:
        raise ValueError("conversion report is incomplete")
    rows = report.get("position_results")
    if not isinstance(rows, list):
        raise ValueError("conversion report lacks paired position_results")
    result: dict[int, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed conversion position result")
        index = row.get("index")
        outcome = row.get("result")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError(f"invalid conversion source index {index!r}")
        if index in result:
            raise ValueError(f"duplicate conversion source index {index}")
        if outcome not in {"win", "draw", "loss"}:
            # Errors and skipped draw-labelled roots are not valid paired
            # conversion observations.
            continue
        result[index] = int(outcome == "win")
    return result


def _trinomial_sum_distribution(
    n: int,
    probability_minus: float,
    probability_zero: float,
    probability_plus: float,
) -> dict[int, float]:
    distribution = {0: 1.0}
    probabilities = (
        (-1, probability_minus),
        (0, probability_zero),
        (1, probability_plus),
    )
    for _ in range(n):
        updated: dict[int, float] = {}
        for total, mass in distribution.items():
            for step, probability in probabilities:
                if probability:
                    updated[total + step] = (
                        updated.get(total + step, 0.0) + mass * probability
                    )
        distribution = updated
    return distribution


def _discrete_quantile(distribution: dict[int, float], probability: float) -> int:
    cumulative = 0.0
    for value in sorted(distribution):
        cumulative += distribution[value]
        if cumulative + 1e-15 >= probability:
            return value
    return max(distribution)


def paired_conversion(
    hard: dict[str, Any],
    uniform: dict[str, Any],
) -> dict[str, Any]:
    hard_wins = _position_wins(hard)
    uniform_wins = _position_wins(uniform)
    common = sorted(set(hard_wins) & set(uniform_wins))
    if not common:
        raise ValueError("paired conversion comparison has no common positions")
    differences = [hard_wins[index] - uniform_wins[index] for index in common]
    minus = differences.count(-1)
    zero = differences.count(0)
    plus = differences.count(1)
    n = len(common)
    distribution = _trinomial_sum_distribution(
        n, minus / n, zero / n, plus / n
    )

    def interval(confidence: float) -> list[float]:
        alpha = 1.0 - confidence
        return [
            _discrete_quantile(distribution, alpha / 2.0) / n,
            _discrete_quantile(distribution, 1.0 - alpha / 2.0) / n,
        ]

    return {
        "n_common": n,
        "hard_replay_rate": sum(hard_wins[index] for index in common) / n,
        "uniform_replay_rate": sum(uniform_wins[index] for index in common) / n,
        "delta_hard_minus_uniform": sum(differences) / n,
        "ci90": interval(0.90),
        "ci95": interval(0.95),
        "uniform_win_to_hard_nonwin": minus,
        "same_conversion_status": zero,
        "uniform_nonwin_to_hard_win": plus,
        "draws_count_as_nonconversion": True,
        "confidence_method": "exact_empirical_trinomial_bootstrap_distribution",
    }


def compact_conversion(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report[key]
        for key in (
            "n_pos",
            "n_win",
            "n_draw",
            "n_loss",
            "n_skipped_draw_label",
            "n_errors",
            "error_rate",
            "conversion",
        )
    }


def compact_coverage(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("stage") != "l3_bucket_visits":
        raise ValueError("unexpected coverage report stage")
    if int(report["geometry"]["trained_buckets_total"]) != 2_125_768:
        raise ValueError("unexpected coverage geometry")
    coverage = report["coverage"]
    return {
        "records": int(report["corpus"]["total_records"]),
        "visited_buckets": int(coverage["visited_buckets"]),
        "coverage_fraction": float(coverage["coverage_fraction"]),
        "ge_10": int(coverage["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(coverage["buckets_with_at_least"]["ge_100"]),
        "gini": float(report["concentration"]["gini"]),
    }


def build_readout(
    *,
    force_dir: Path,
    conversion_dir: Path,
    training_summary_path: Path,
    opening_manifest_path: Path,
    expected_games_per_view: int,
    expected_openings: int,
    code_sha: str,
    source_job: str,
    source_attempt: str,
    source_code_sha: str,
    expected_uniform_sha: str,
    expected_hard_sha: str,
) -> dict[str, Any]:
    training = load(training_summary_path)
    openings = load(opening_manifest_path)
    if (
        training.get("verdict") != "L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY"
        or training.get("code_sha") != source_code_sha
        or training.get("primary_contrast")
        != "HARD_REPLAY minus UNIFORM_REPLAY"
        or training.get("design", {}).get("single_factor")
        != "historical_replay_selection_policy"
        or training.get("design", {}).get("same_parent") is not True
        or training.get("design", {}).get("same_fresh_corpus") is not True
        or training.get("design", {}).get("same_fit") is not True
        or training.get("design", {}).get("same_holdout") is not True
        or training.get("external_teacher_inputs") != 0
        or training.get("promotion_authorized") is not False
        or training.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError("hard-replay training certificate mismatch")
    arms = training.get("arms", {})
    if (
        arms.get("UNIFORM_REPLAY", {}).get("model_sha256")
        != expected_uniform_sha
        or arms.get("HARD_REPLAY", {}).get("model_sha256") != expected_hard_sha
        or arms.get("UNIFORM_REPLAY", {}).get("optimizer", {}).get("success")
        is not True
        or arms.get("HARD_REPLAY", {}).get("optimizer", {}).get("success")
        is not True
    ):
        raise ValueError("hard-replay model hash/convergence mismatch")
    if (
        openings.get("records") != expected_openings
        or openings.get("unique_records") != expected_openings
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        view: force_cell(
            force_dir / f"force-{view}-HARD_REPLAY-vs-UNIFORM_REPLAY.json",
            expected_games_per_view,
        )
        for view in ("q00", "native")
    }
    summed_force = summarize_force_counts(
        sum(force[view]["wins_hard_replay"] for view in force),
        sum(force[view]["draws"] for view in force),
        sum(force[view]["wins_uniform_replay"] for view in force),
    )

    conversion: dict[str, Any] = {}
    for stratum in ("p3_mince", "p4_egal"):
        hard = load(conversion_dir / f"HARD_REPLAY-{stratum}.json")
        uniform = load(conversion_dir / f"UNIFORM_REPLAY-{stratum}.json")
        conversion[stratum] = {
            "HARD_REPLAY": compact_conversion(hard),
            "UNIFORM_REPLAY": compact_conversion(uniform),
            "paired_delta_hard_minus_uniform": paired_conversion(hard, uniform),
        }

    coverage = {
        name: compact_coverage(arms[name]["coverage"])
        for name in ("UNIFORM_REPLAY", "HARD_REPLAY")
    }
    coverage_delta = {
        key: coverage["HARD_REPLAY"][key] - coverage["UNIFORM_REPLAY"][key]
        for key in (
            "visited_buckets",
            "coverage_fraction",
            "ge_10",
            "ge_100",
            "gini",
        )
    }

    force_both_positive = all(
        force[view]["rate_hard_replay"] > 0.5 for view in force
    )
    force_both_nonregressed = all(force[view]["ci95"][1] >= 0.5 for view in force)
    conversion_nonregressed = all(
        conversion[stratum]["paired_delta_hard_minus_uniform"]["ci95"][1] >= 0.0
        for stratum in conversion
    )
    if (
        force_both_positive
        and summed_force["ci95"][0] > 0.5
        and conversion_nonregressed
    ):
        verdict = ABOVE_95
    elif (
        force_both_positive
        and summed_force["ci90"][0] > 0.5
        and conversion_nonregressed
    ):
        verdict = ABOVE_90
    elif (
        summed_force["ci90"][1] < 0.5
        or not force_both_nonregressed
        or not conversion_nonregressed
    ):
        verdict = BELOW
    elif (
        summed_force["rate_hard_replay"] > 0.5
        and force_both_nonregressed
        and conversion_nonregressed
    ):
        verdict = DIRECTIONAL
    else:
        verdict = INCONCLUSIVE

    return {
        "schema": 1,
        "verdict": verdict,
        "code_sha": code_sha,
        "source": {
            "job_id": source_job,
            "attempt_id": source_attempt,
            "code_sha": source_code_sha,
        },
        "models": {
            "UNIFORM_REPLAY_sha256": expected_uniform_sha,
            "HARD_REPLAY_sha256": expected_hard_sha,
        },
        "protocol": {
            "primary_contrast": "HARD_REPLAY minus UNIFORM_REPLAY",
            "single_training_factor": "historical_replay_selection_policy",
            "paired_colours": True,
            "fresh_disjoint_openings": True,
            "openings": expected_openings,
            "games_per_view": expected_games_per_view,
            "views": ["q00_depth9", "native_movetime_0.1"],
            "conversion_strata": ["p3_mince", "p4_egal"],
            "holdout_is_diagnostic_only": True,
            "holdout_not_used_for_selection": True,
        },
        "opening_manifest": openings,
        "force": force,
        "force_views_summed": summed_force,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_hard_minus_uniform": coverage_delta,
        "assembly_signal_profile": training["assembly"],
        "decision_evidence": {
            "both_force_views_point_positive": force_both_positive,
            "both_force_views_regression_not_established_95": force_both_nonregressed,
            "summed_force_superiority_90": summed_force["ci90"][0] > 0.5,
            "summed_force_superiority_95": summed_force["ci95"][0] > 0.5,
            "conversion_regression_not_established_95": conversion_nonregressed,
        },
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--conversion-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-games-per-view", required=True, type=int)
    parser.add_argument("--expected-openings", required=True, type=int)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--uniform-model-sha", required=True)
    parser.add_argument("--hard-model-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args(argv)
    payload = build_readout(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        training_summary_path=args.training_summary,
        opening_manifest_path=args.opening_manifest,
        expected_games_per_view=args.expected_games_per_view,
        expected_openings=args.expected_openings,
        code_sha=args.code_sha,
        source_job=args.source_job,
        source_attempt=args.source_attempt,
        source_code_sha=args.source_code_sha,
        expected_uniform_sha=args.uniform_model_sha,
        expected_hard_sha=args.hard_model_sha,
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
