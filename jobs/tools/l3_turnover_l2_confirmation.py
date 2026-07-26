#!/usr/bin/env python3
"""Aggregate the preregistered independent confirmation of the L2_1E5 arm.

``home-0987`` closed the fixed-corpus L2 screen with
``TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW``: ``L2_1E5`` placed both
point estimates above the ``L2_3E5_CONTROL`` control without either Wilson
lower bound clearing 50 %.  The preregistered decision rule allows exactly one
follow-up, an independent confirmation of the same immutable model on a fresh
opening pool.  This module consumes that fresh readout, pools it with the
``home-0987`` cells and emits the confirmation verdict.

Nothing here selects on holdout loss, gradient norm or weight amplitude: those
stay diagnostics.  No verdict authorises a promotion.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

CHAMPION_REVIEW = "L2_1E5_CHAMPION_CONFIRMATION_REVIEW_READY"
EFFECT_CONFIRMED = "L2_1E5_EFFECT_CONFIRMED_HUMAN_REVIEW"
DIRECTION_REPLICATED = "L2_1E5_DIRECTION_REPLICATED_REVIEW"
NOT_REPLICATED = "L2_1E5_DIRECTION_NOT_REPLICATED_RETAIN_3E5"

PREVIOUS_VERDICT = "TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW"
PREVIOUS_RECOMMENDATION = "independent_confirmation_of_directional_l2_arms"
PREVIOUS_OPENING_SEED = 1836313
PREVIOUS_OPENING_SHA = (
    "e7b89a5e3feade8919c8a498f424084deb0a2128c1712c9ca0a9547cf22b6df2"
)

CANDIDATE_MODEL_SHA = (
    "27cf9bedf20d00bbcc106a52ad183990f8df131362c4590fc319cc708464ff49"
)
CONTROL_MODEL_SHA = (
    "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
)
F2M_MODEL_SHA = (
    "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
)
TURNOVER_CORPUS_SHA = (
    "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
)
TURNOVER_META_SHA = (
    "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
)

ARM = "L2_1E5"
CONTROL = "TURNOVER"
CHAMPION = "F2M"
OPPONENTS = (CONTROL, CHAMPION)
VIEWS = ("q00", "native")
PREVIOUS_GAMES = 1_000
FRESH_GAMES = 2_000
POOLED_GAMES = PREVIOUS_GAMES + FRESH_GAMES


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
    """Authenticate the home-0987 screen certificate and extract its cells."""
    training = previous.get("training_summary", {})
    arms = training.get("arms", {})
    control = training.get("control", {})
    openings = previous.get("opening_manifest", {})

    if (
        previous.get("verdict") != PREVIOUS_VERDICT
        or previous.get("recommendation") != PREVIOUS_RECOMMENDATION
        or previous.get("recommended_l2_arm") != ARM
        or previous.get("directional_arms") != [ARM]
        or previous.get("confirmed_leads") != []
        or previous.get("eligible_for_guard_cells") != [ARM]
        or previous.get("promotion_authorized") is not False
        or previous.get("automatic_next_job") is not None
    ):
        raise ValueError("previous L2 screen certificate mismatch")

    guardrails = previous.get("guardrails", {}).get(ARM, {})
    if guardrails.get("all_pass") is not True or not all(
        guardrails.get("checks", {}).values()
    ):
        raise ValueError("previous L2 screen guardrails did not all pass")

    if (
        arms.get(ARM, {}).get("model_sha256") != CANDIDATE_MODEL_SHA
        or arms.get(ARM, {}).get("l2") != 1e-05
        or control.get("model_sha256") != CONTROL_MODEL_SHA
        or control.get("l2") != 3e-05
        or training.get("parent_model_sha256") != F2M_MODEL_SHA
        or training.get("training_corpus_sha256") != TURNOVER_CORPUS_SHA
        or training.get("training_meta_sha256") != TURNOVER_META_SHA
        or training.get("experiment_variant") != "TURNOVER_1_1_L2_SCREEN"
        or training.get("training_records") != 2_000_000
        or training.get("new_generation_performed") is not False
        or training.get("external_teacher_inputs") != 0
    ):
        raise ValueError("previous L2 model/training identity mismatch")

    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != PREVIOUS_OPENING_SEED
        or openings.get("sha256") != PREVIOUS_OPENING_SHA
    ):
        raise ValueError("previous L2 opening-pool identity mismatch")

    primary = previous.get("primary_checks", {}).get(ARM, {})
    force: dict[str, dict[str, Any]] = {}
    for opponent in OPPONENTS:
        for view in VIEWS:
            key = f"{view}_{ARM}_vs_{opponent}"
            force[f"{view}_vs_{opponent}"] = validate_force_row(
                previous.get("force", {}).get(key, {}),
                expected_n=PREVIOUS_GAMES,
                label=f"previous {key}",
                require_complete=False,
            )
    for view in VIEWS:
        if primary.get(view) != {
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
) -> dict[str, Any]:
    if (
        openings.get("records") != FRESH_GAMES // 2
        or openings.get("unique_records") != FRESH_GAMES // 2
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != expected_seed
        or openings.get("sha256") != expected_sha256
        or openings.get("candidate_sha256") != expected_candidate_sha256
        or openings.get("mode") != "deterministic-ordered-filter"
    ):
        raise ValueError("confirmation opening-pool identity mismatch")
    if openings.get("sha256") == PREVIOUS_OPENING_SHA:
        raise ValueError("confirmation pool must differ from the screen pool")
    return openings


def build_confirmation(
    *,
    force_dir: Path,
    previous: dict[str, Any],
    openings: dict[str, Any],
) -> dict[str, Any]:
    previous_force = validate_previous(previous)

    fresh: dict[str, dict[str, Any]] = {}
    pooled: dict[str, dict[str, Any]] = {}
    fresh_checks: dict[str, dict[str, Any]] = {CONTROL: {}, CHAMPION: {}}
    pooled_checks: dict[str, dict[str, Any]] = {CONTROL: {}, CHAMPION: {}}

    for opponent in OPPONENTS:
        for view in VIEWS:
            key = f"{view}_vs_{opponent}"
            row = validate_force_row(
                load(force_dir / f"force-{view}-{ARM}-vs-{opponent}.json"),
                expected_n=FRESH_GAMES,
                label=f"fresh {key}",
                require_complete=True,
            )
            fresh[key] = row
            pooled[key] = combine_rows(previous_force[key], row)
            fresh_checks[opponent][view] = checks(row)
            pooled_checks[opponent][view] = checks(pooled[key])
            if int(pooled[key]["n"]) != POOLED_GAMES:
                raise ValueError(f"{key}: pooled cell is not {POOLED_GAMES} games")

    champion_regression_free = all(
        fresh_checks[CHAMPION][view]["regression_not_established"]
        and pooled_checks[CHAMPION][view]["regression_not_established"]
        for view in VIEWS
    )
    control_confirmed = all(
        fresh_checks[CONTROL][view]["superiority_established"]
        and pooled_checks[CONTROL][view]["superiority_established"]
        for view in VIEWS
    )
    champion_superior = all(
        fresh_checks[CHAMPION][view]["superiority_established"]
        and pooled_checks[CHAMPION][view]["superiority_established"]
        for view in VIEWS
    )
    direction_replicated = all(
        fresh_checks[CONTROL][view]["positive_point_estimate"] for view in VIEWS
    )

    if control_confirmed and champion_superior and champion_regression_free:
        verdict = CHAMPION_REVIEW
        recommendation = "human_review_l2_1e5_as_general_champion_candidate"
    elif control_confirmed and champion_regression_free:
        verdict = EFFECT_CONFIRMED
        recommendation = "human_review_l2_1e5_before_replay_cross"
    elif direction_replicated and champion_regression_free:
        verdict = DIRECTION_REPLICATED
        recommendation = "human_review_replicated_direction_without_established_lead"
    else:
        verdict = NOT_REPLICATED
        recommendation = "retain_l2_3e5_and_close_l2_factor"

    return {
        "schema": 1,
        "verdict": verdict,
        "recommendation": recommendation,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "all_guardrails_pass": champion_regression_free,
        "protocol": {
            "candidate": ARM,
            "candidate_l2": 1e-05,
            "causal_control": "L2_3E5_CONTROL",
            "champion": CHAMPION,
            "changed_factor": "independent_evaluation_sample_only",
            "same_immutable_model": True,
            "fixed_corpus": "TURNOVER_1_1",
            "confirmation_openings": FRESH_GAMES // 2,
            "confirmation_games_per_cell": FRESH_GAMES,
            "previous_games_per_cell": PREVIOUS_GAMES,
            "pooled_games_per_cell": POOLED_GAMES,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "paired_colors": True,
            "rerun_static_guardrails": False,
        },
        "candidate_model_sha256": CANDIDATE_MODEL_SHA,
        "control_model_sha256": CONTROL_MODEL_SHA,
        "fresh_force": fresh,
        "fresh_checks": fresh_checks,
        "pooled_force": pooled,
        "pooled_checks": pooled_checks,
        "guardrails": {
            "fresh_champion_regression_not_established": all(
                fresh_checks[CHAMPION][view]["regression_not_established"]
                for view in VIEWS
            ),
            "pooled_champion_regression_not_established": all(
                pooled_checks[CHAMPION][view]["regression_not_established"]
                for view in VIEWS
            ),
            "fresh_pool_independent": True,
            "source_model_identity_unchanged": True,
            "source_screen_guardrails_all_pass": True,
        },
        "opening_manifest": openings,
        "previous_screen_certificate": {
            "verdict": previous["verdict"],
            "recommendation": previous["recommendation"],
            "recommended_l2_arm": previous["recommended_l2_arm"],
            "force": previous_force,
            "opening_manifest": previous.get("opening_manifest", {}),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", type=Path, required=True)
    parser.add_argument("--previous-evaluation", type=Path, required=True)
    parser.add_argument("--opening-manifest", type=Path, required=True)
    parser.add_argument("--expected-opening-seed", type=int, required=True)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    openings = validate_openings(
        load(args.opening_manifest),
        expected_seed=args.expected_opening_seed,
        expected_sha256=args.expected_opening_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
    )
    report = build_confirmation(
        force_dir=args.force_dir,
        previous=load(args.previous_evaluation),
        openings=openings,
    )
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.summary_out:
        args.summary_out.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
    print(report["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
