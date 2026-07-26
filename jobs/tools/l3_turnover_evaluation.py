#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE 1:1 temporal-turnover test."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import paired_conversion
except ModuleNotFoundError:
    from jobs.tools.l3_corrected_conversion_matrix import paired_conversion


PROMOTION = "TURNOVER_PROMOTION_REVIEW_READY"
EFFECT = "TURNOVER_EFFECT_CONFIRMED_REVIEW"
DIRECTIONAL = "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
PLATEAU = "TURNOVER_PLATEAU_OR_REGRESSION_REVIEW"
M2_D8_CODE_SHA = "012b9c716dadf2c3df668c23a7dd9d5ece423b8c"
M2_D8_MODEL_SHA = "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
M2_D8_CORPUS_SHA = "ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8"
M2_D8_META_SHA = "42b184456375bb581192651262f3981879bd04e5ee3162a6186883c2f8f66729"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def force_row(path: Path) -> dict[str, Any]:
    value = load(path)
    keys = ("n", "wins_a", "draws", "wins_b", "rate", "elo", "ci_low", "ci_high")
    row = {key: value[key] for key in keys}
    if int(row["n"]) != 1_000:
        raise ValueError(f"{path}: expected 1000 games")
    return row


def compact_coverage(path: Path) -> dict[str, Any]:
    report = load(path)
    if report.get("stage") != "l3_bucket_visits":
        raise ValueError(f"{path}: unexpected coverage stage")
    if int(report["geometry"]["trained_buckets_total"]) != 2_125_768:
        raise ValueError(f"{path}: unexpected 8cf geometry")
    coverage = report["coverage"]
    return {
        "records": int(report["corpus"]["total_records"]),
        "visited_buckets": int(coverage["visited_buckets"]),
        "ge_10": int(coverage["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(coverage["buckets_with_at_least"]["ge_100"]),
        "gini": float(report["concentration"]["gini"]),
    }


def independent_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    p1, p0 = float(candidate["rate"]), float(baseline["rate"])
    n1, n0 = int(candidate["n"]), int(baseline["n"])
    delta = p1 - p0
    se = math.sqrt(p1 * (1.0 - p1) / n1 + p0 * (1.0 - p0) / n0)
    return {
        "delta": delta,
        "ci_low": delta - 1.96 * se,
        "ci_high": delta + 1.96 * se,
        "independent_pools": True,
    }


def _check_depth_factor_closed(evaluation: dict[str, Any]) -> None:
    guardrails = evaluation.get("guardrails", {})
    failed = sorted(key for key, value in guardrails.items() if not value)
    if (
        evaluation.get("verdict") != "D12_PLATEAU_OR_REGRESSION_REVIEW"
        or evaluation.get("recommendation")
        != "stop_single_depth_escalation_and_prepare_distribution_factor"
        or evaluation.get("all_guardrails_pass") is not False
        or failed != ["f2m_q00_regression_not_established"]
    ):
        raise ValueError("D12 depth-factor closure certificate mismatch")


def build_evaluation(
    *,
    force_dir: Path,
    conversion_dir: Path,
    coverage_dir: Path,
    training_summary_path: Path,
    m2_training_summary_path: Path,
    m2_corpus_contract_path: Path,
    m2_evaluation_path: Path,
    d12_evaluation_path: Path,
    opening_manifest_path: Path,
    expected_opening_seed: int,
    expected_opening_sha256: str,
    bootstrap_samples: int = 200_000,
    seed: int = 978_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    m2_training = load(m2_training_summary_path)
    m2_contract = load(m2_corpus_contract_path)
    m2_evaluation = load(m2_evaluation_path)
    d12_evaluation = load(d12_evaluation_path)
    openings = load(opening_manifest_path)

    if (
        training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or training.get("parent") != "F2M"
        or training.get("fresh_only") is not False
        or training.get("experiment_variant") != "TURNOVER_1_1"
        or training.get("play_depth") != 8
        or training.get("training_records") != 2_000_000
        or training.get("historical_replay_records") != 1_000_000
        or training.get("fresh_records") != 1_000_000
        or training.get("temporal_distribution_records")
        != {"fresh_m2": 1_000_000, "parent_f2m": 1_000_000}
        or training.get("new_generation_performed") is not False
    ):
        raise ValueError("turnover training contract mismatch")
    if (
        m2_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or m2_training.get("parent") != "F2M"
        or m2_training.get("fresh_only") is not True
        or m2_training.get("code_sha") != M2_D8_CODE_SHA
        or m2_training.get("model_sha256") != M2_D8_MODEL_SHA
        or m2_training.get("training_corpus_sha256") != M2_D8_CORPUS_SHA
        or m2_training.get("training_records") != 2_000_000
        or m2_contract.get("jnnw_sha256") != M2_D8_CORPUS_SHA
        or m2_contract.get("jsm_sha256") != M2_D8_META_SHA
        or m2_contract.get("records") != 2_000_000
        or m2_contract.get("parent") != "F2M"
        or m2_contract.get("fresh_only") is not True
        or m2_contract.get("historical_replay_records") != 0
        or m2_contract.get("base_seed") != 1_618_033
        or m2_contract.get("starts") != "standard"
        or m2_contract.get("top3") is not False
        or m2_contract.get("role_reweight_v2") is not False
        or m2_contract.get("geometry") != "8cf"
        or m2_contract.get("search") != "Q00"
    ):
        raise ValueError("M2 d8 legacy fresh-only control contract mismatch")
    if (
        m2_evaluation.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW"
        or m2_evaluation.get("recommendation")
        != "stop_same_recipe_and_prepare_d10_causal_arm"
        or m2_evaluation.get("all_guardrails_pass") is not True
        or m2_evaluation.get("training_summary", {}).get("model_sha256")
        != m2_training.get("model_sha256")
    ):
        raise ValueError("M2 plateau certificate mismatch")
    _check_depth_factor_closed(d12_evaluation)

    excluded = openings.get("excluded_sources", {})
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != expected_opening_seed
        or openings.get("sha256") != expected_opening_sha256
        or not any(str(path).endswith("prior-m2-independent.fen") for path in excluded)
        or not any(str(path).endswith("prior-d10-independent.fen") for path in excluded)
        or not any(str(path).endswith("prior-d12-independent.fen") for path in excluded)
    ):
        raise ValueError("turnover independent opening-pool contract mismatch")

    force = {
        f"{view}_vs_{opponent}": force_row(
            force_dir / f"force-{view}-TURNOVER-vs-{opponent}.json"
        )
        for view in ("q00", "native")
        for opponent in ("M2", "F2M", "GEN2")
    }
    primary = {
        opponent: {
            view: {
                "positive_point_estimate": force[f"{view}_vs_{opponent}"]["rate"] > 0.5,
                "superiority_established": force[f"{view}_vs_{opponent}"]["ci_low"]
                > 0.5,
                "regression_not_established": force[f"{view}_vs_{opponent}"]["ci_high"]
                >= 0.5,
            }
            for view in ("q00", "native")
        }
        for opponent in ("M2", "F2M")
    }

    conversion: dict[str, Any] = {}
    for stratum_index, stratum in enumerate(("p3_mince", "p4_egal")):
        reports = {
            model: load(conversion_dir / f"{model}-{stratum}.json")
            for model in ("TURNOVER", "M2", "F2M")
        }
        conversion[stratum] = {
            model: {
                key: reports[model][key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
            for model in reports
        }
        for control_index, control in enumerate(("M2", "F2M")):
            conversion[stratum][
                f"paired_delta_turnover_minus_{control.lower()}"
            ] = paired_conversion(
                reports["TURNOVER"],
                reports[control],
                seed=seed + 10 * stratum_index + control_index,
                bootstrap_samples=bootstrap_samples,
            )

    coverage = {
        model: compact_coverage(coverage_dir / f"{model}-coverage.json")
        for model in ("TURNOVER", "M2", "F2M")
    }
    coverage_delta = {
        control: {
            "visited_buckets": (
                coverage["TURNOVER"]["visited_buckets"]
                - coverage[control]["visited_buckets"]
            ),
            "ge_100": coverage["TURNOVER"]["ge_100"] - coverage[control]["ge_100"],
        }
        for control in ("M2", "F2M")
    }
    gen2_delta = {
        view: independent_delta(
            force[f"{view}_vs_GEN2"],
            m2_evaluation["force"][f"{view}_vs_GEN2"],
        )
        for view in ("q00", "native")
    }

    guardrails: dict[str, bool] = {}
    for control in ("M2", "F2M"):
        for view in ("q00", "native"):
            guardrails[f"{control.lower()}_{view}_regression_not_established"] = (
                primary[control][view]["regression_not_established"]
            )
    for view in ("q00", "native"):
        guardrails[f"gen2_{view}_gross_regression_not_observed"] = (
            force[f"{view}_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta[view]["delta"] >= -0.03
        )
    for stratum in ("p3_mince", "p4_egal"):
        guardrails[f"{stratum}_absolute_conversion_floor"] = (
            float(conversion[stratum]["TURNOVER"]["conversion"]) >= 0.95
        )
        for control in ("m2", "f2m"):
            guardrails[
                f"{stratum}_regression_over_3pp_vs_{control}_not_established"
            ] = (
                conversion[stratum][
                    f"paired_delta_turnover_minus_{control}"
                ]["ci_high"]
                >= -0.03
            )
    for control in ("M2", "F2M"):
        guardrails[f"visited_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["TURNOVER"]["visited_buckets"]
            >= 0.95 * coverage[control]["visited_buckets"]
        )
        guardrails[f"ge100_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["TURNOVER"]["ge_100"] >= 0.95 * coverage[control]["ge_100"]
        )

    all_guardrails = all(guardrails.values())
    effect_superior = all(
        primary["M2"][view]["superiority_established"]
        for view in ("q00", "native")
    )
    champion_superior = effect_superior and all(
        primary["F2M"][view]["superiority_established"]
        for view in ("q00", "native")
    )
    directional = all(
        primary["M2"][view]["positive_point_estimate"]
        and primary["M2"][view]["regression_not_established"]
        and primary["F2M"][view]["regression_not_established"]
        for view in ("q00", "native")
    )
    if champion_superior and all_guardrails:
        verdict = PROMOTION
        recommendation = "human_review_turnover_promotion_and_next_scale"
    elif effect_superior and all_guardrails:
        verdict = EFFECT
        recommendation = "human_review_turnover_effect_before_champion_confirmation"
    elif directional and all_guardrails:
        verdict = DIRECTIONAL
        recommendation = "independent_turnover_confirmation"
    else:
        verdict = PLATEAU
        recommendation = "close_turnover_1to1_and_preregister_next_single_factor"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "TURNOVER_1_1",
            "causal_control": "M2_D8_FRESH2M",
            "champion": "F2M",
            "historical_guardrail": "GEN2_MMTO",
            "games_per_force_view": 1_000,
            "openings": 500,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "conversion_positions_per_stratum": 300,
            "changed_factor": "temporal_replay_distribution",
            "fixed_training_volume": 2_000_000,
            "parent_replay_records": 1_000_000,
            "fresh_m2_records": 1_000_000,
        },
        "force": force,
        "turnover_minus_m2_gen2_independent_delta": gen2_delta,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_turnover_minus_controls": coverage_delta,
        "primary_checks": primary,
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails,
        "recommendation": recommendation,
        "training_summary": training,
        "m2_training_summary": m2_training,
        "m2_corpus_contract": m2_contract,
        "m2_plateau_certificate": m2_evaluation,
        "d12_depth_factor_closure": d12_evaluation,
        "opening_manifest": openings,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--conversion-dir", required=True, type=Path)
    parser.add_argument("--coverage-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--m2-training-summary", required=True, type=Path)
    parser.add_argument("--m2-corpus-contract", required=True, type=Path)
    parser.add_argument("--m2-evaluation", required=True, type=Path)
    parser.add_argument("--d12-evaluation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-opening-seed", required=True, type=int)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=978_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
        m2_training_summary_path=args.m2_training_summary,
        m2_corpus_contract_path=args.m2_corpus_contract,
        m2_evaluation_path=args.m2_evaluation,
        d12_evaluation_path=args.d12_evaluation,
        opening_manifest_path=args.opening_manifest,
        expected_opening_seed=args.expected_opening_seed,
        expected_opening_sha256=args.expected_opening_sha256,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
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
