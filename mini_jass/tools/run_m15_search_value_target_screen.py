#!/usr/bin/env python3
"""M15: screen deployable value targets against the M14 oracle upper bound.

M14 showed that exact value labels restore L2 value learning. M15 keeps the
frozen M13 protocol, twenty seeds, generated positions, search traces, policy
targets, optimizer and evaluation cohorts fixed, and changes only the VALUE
label consumed by training:

- selfplay_outcome: honest M13 baseline;
- search_root_score: bounded-negamax root score already produced by self-play;
- outcome_search_blend: 50/50 terminal outcome and root search score;
- exact_oracle: diagnostic upper bound inherited from M14, never promotable.

The L2 loop has one generation, so changing the training label cannot alter the
generated trajectory or search trace for a paired seed. Search-derived labels
never consult solved oracle values.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
from typing import Any, Callable

import numpy as np
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.selfplay import GenerationResult  # noqa: E402
import mini_jass_lab.seed_variance_replication as m13  # noqa: E402


SCHEMA = "mini_jass.m15_search_value_target_screen.v1"
EXPECTED_SEEDS = list(range(132001, 132021))
EXPECTED_ARMS = {
    "baseline": {"value_target_source": "selfplay_outcome"},
    "search": {"value_target_source": "search_root_score"},
    "blend": {"value_target_source": "outcome_search_blend", "search_weight": 0.50},
    "oracle": {"value_target_source": "exact_oracle"},
}


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M15":
        raise ValueError("unexpected M15 schema")
    if config.get("expected_execution_host") != "cpx62":
        raise ValueError("M15 must remain cpx62-routed")
    if config.get("paired_seeds") != EXPECTED_SEEDS:
        raise ValueError("M15 must reuse the exact M13/M14 twenty seeds")
    if config.get("arms") != EXPECTED_ARMS:
        raise ValueError("M15 arm definitions changed")
    if config.get("oracle_role") != "diagnostic_upper_bound_only":
        raise ValueError("M15 oracle arm must remain diagnostic-only")
    if config.get("promotion_policy") != "no_m15_arm_promotable":
        raise ValueError("M15 is a screening experiment, not a promotion gate")
    base = (path.parent / str(config["base_replication_config"])).resolve()
    resolved_m13 = m13.resolve_seed_variance_replication_config(base)
    if resolved_m13["paired_seeds"] != EXPECTED_SEEDS:
        raise ValueError("M15/M13 paired seeds diverged")
    resolved = dict(config)
    resolved["base_replication_config"] = str(base)
    return resolved


def _search_targeted_generation(
    original_generate: Callable[..., GenerationResult],
    source: str,
    search_weight: float,
) -> Callable[..., GenerationResult]:
    """Return a generator wrapper that changes only ReplaySample.value_target."""

    def wrapped(*args: Any, **kwargs: Any) -> GenerationResult:
        generated = original_generate(*args, **kwargs)
        trace = generated.metrics.get("search_trace", [])
        root_scores = {
            (int(row["game_id"]), int(row["ply"])): float(row["root_score"])
            for row in trace
        }
        rebuilt = []
        for sample in generated.samples:
            key = (int(sample.game_id), int(sample.ply))
            if key not in root_scores:
                raise ValueError(f"M15 missing root score for generated sample {key}")
            search_value = float(np.clip(root_scores[key], -1.0, 1.0))
            if source == "search_root_score":
                target = search_value
            elif source == "outcome_search_blend":
                target = (
                    search_weight * search_value
                    + (1.0 - search_weight) * float(sample.value_target)
                )
            else:
                raise ValueError(f"unknown M15 search target source: {source}")
            rebuilt.append(replace(sample, value_target=float(target)))
        metrics = dict(generated.metrics)
        metrics["m15_value_target"] = {
            "source": source,
            "search_weight": float(search_weight),
            "uses_oracle": False,
            "sample_count": len(rebuilt),
        }
        return GenerationResult(samples=rebuilt, metrics=metrics, coverage=generated.coverage)

    return wrapped


def _run_arm(
    *,
    arm: str,
    base_config: Path,
    oracle: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str,
) -> dict[str, Any]:
    original_execute = m13.execute_loop
    original_generate = loop_module.generate_self_play
    spec = EXPECTED_ARMS[arm]
    source = str(spec["value_target_source"])
    try:
        if source == "exact_oracle":
            def execute_with_oracle(*args: Any, **kwargs: Any) -> Any:
                kwargs["value_target_source"] = "exact_oracle"
                return original_execute(*args, **kwargs)
            m13.execute_loop = execute_with_oracle
        elif source in {"search_root_score", "outcome_search_blend"}:
            loop_module.generate_self_play = _search_targeted_generation(
                original_generate,
                source,
                float(spec.get("search_weight", 1.0)),
            )
        return m13.run_seed_variance_replication(
            base_config,
            oracle,
            run_dir,
            compact_output,
            execution_host,
        )
    finally:
        m13.execute_loop = original_execute
        loop_module.generate_self_play = original_generate


def _mean_target_value_mae(result: dict[str, Any]) -> float:
    return float(np.mean([
        float(row["targets"]["value_mae"]) for row in result["seed_results"]
    ]))


def _arm_metrics(result: dict[str, Any]) -> dict[str, float | int | str]:
    aggregate = result["aggregate"]
    return {
        "status": str(result["status"]),
        "successful_run_count": int(result["pack"]["successful_run_count"]),
        "eligible_candidate_count": int(aggregate["eligible_candidate_count"]),
        "mean_confirmation_value_sign_delta": float(
            aggregate["mean_confirmation_value_sign_delta"]
        ),
        "mean_development_value_sign_delta": float(
            aggregate["mean_development_value_sign_delta"]
        ),
        "mean_confirmation_optimal_mass_delta": float(
            aggregate["mean_confirmation_optimal_mass_delta"]
        ),
        "mean_development_optimal_mass_delta": float(
            aggregate["mean_development_optimal_mass_delta"]
        ),
        "mean_target_value_exact_rate": float(aggregate["mean_target_value_exact_rate"]),
        "mean_target_value_mae": _mean_target_value_mae(result),
        "mean_target_optimal_mass": float(aggregate["mean_target_optimal_mass"]),
    }


def _contrast(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in (
        "mean_confirmation_value_sign_delta",
        "mean_development_value_sign_delta",
        "mean_confirmation_optimal_mass_delta",
        "mean_development_optimal_mass_delta",
        "mean_target_value_exact_rate",
        "mean_target_value_mae",
    ):
        result[key] = float(candidate[key]) - float(baseline[key])
    return result


def _paired_value_deltas(candidate: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    left = {int(row["seed"]): row for row in baseline["seed_results"]}
    right = {int(row["seed"]): row for row in candidate["seed_results"]}
    rows = []
    for seed in EXPECTED_SEEDS:
        rows.append({
            "seed": seed,
            "confirmation_value_sign_delta": float(
                right[seed]["confirmation"]["value_sign_delta"]
                - left[seed]["confirmation"]["value_sign_delta"]
            ),
            "development_value_sign_delta": float(
                right[seed]["development"]["value_sign_delta"]
                - left[seed]["development"]["value_sign_delta"]
            ),
            "confirmation_optimal_mass_delta": float(
                right[seed]["confirmation"]["optimal_mass_delta"]
                - left[seed]["confirmation"]["optimal_mass_delta"]
            ),
            "development_optimal_mass_delta": float(
                right[seed]["development"]["optimal_mass_delta"]
                - left[seed]["development"]["optimal_mass_delta"]
            ),
        })
    return rows


def run_m15(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve_config(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M15 requires cpx62, got {host}")

    base_config = Path(config["base_replication_config"])
    run_dir.mkdir(parents=True, exist_ok=True)
    raw: dict[str, dict[str, Any]] = {}
    for arm in ("baseline", "search", "blend", "oracle"):
        raw[arm] = _run_arm(
            arm=arm,
            base_config=base_config,
            oracle=oracle_path,
            run_dir=run_dir / arm,
            compact_output=run_dir / f"{arm}.m13.json",
            execution_host=host,
        )

    metrics = {arm: _arm_metrics(value) for arm, value in raw.items()}
    baseline = metrics["baseline"]
    oracle = metrics["oracle"]
    oracle_gain = float(oracle["mean_confirmation_value_sign_delta"]) - float(
        baseline["mean_confirmation_value_sign_delta"]
    )
    feasible: dict[str, Any] = {}
    maximum_policy_shift = float(config["success_rule"]["maximum_absolute_policy_mass_delta"])
    for arm in ("search", "blend"):
        contrast = _contrast(metrics[arm], baseline)
        recovery = (
            contrast["mean_confirmation_value_sign_delta"] / oracle_gain
            if oracle_gain > 0.0
            else 0.0
        )
        passes = (
            contrast["mean_confirmation_value_sign_delta"] > 0.0
            and contrast["mean_development_value_sign_delta"] > 0.0
            and recovery >= float(config["success_rule"]["minimum_oracle_gain_recovery_fraction"])
            and abs(contrast["mean_confirmation_optimal_mass_delta"]) <= maximum_policy_shift
            and abs(contrast["mean_development_optimal_mass_delta"]) <= maximum_policy_shift
        )
        feasible[arm] = {
            "contrast_vs_baseline": contrast,
            "oracle_gain_recovery_fraction": float(recovery),
            "scientific_pass": bool(passes),
            "paired_seed_deltas": _paired_value_deltas(raw[arm], raw["baseline"]),
        }

    execution_ok = all(
        result["execution_gate"]["status"] == "PASS"
        and result["pack"]["successful_run_count"] == 20
        for result in raw.values()
    )
    winners = [arm for arm in ("search", "blend") if feasible[arm]["scientific_pass"]]
    selected = max(
        winners,
        key=lambda arm: float(feasible[arm]["oracle_gain_recovery_fraction"]),
        default=None,
    )
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M15",
        "status": "PASS" if execution_ok and selected is not None else "FAIL",
        "execution_gate": {
            "status": "PASS" if execution_ok else "FAIL",
            "criteria": {
                "all_four_arms_completed": execution_ok,
                "same_twenty_paired_seeds": True,
                "one_generation_prevents_target_feedback_into_trajectory": True,
                "cpx62_execution_proven": host == "cpx62",
            },
        },
        "contracts": {
            "execution_host": host,
            "only_intended_factor": "value_target_consumed_by_training",
            "search_targets_use_oracle": False,
            "oracle_arm_diagnostic_only": True,
            "m15_arms_promotable": False,
            "production_jass_changes_authorized": False,
            "direct_10x10_transfer_authorized": False,
        },
        "oracle_upper_bound_gain": {
            "confirmation_value_sign": oracle_gain,
            "development_value_sign": float(oracle["mean_development_value_sign_delta"])
            - float(baseline["mean_development_value_sign_delta"]),
        },
        "arm_metrics": metrics,
        "feasible_target_results": feasible,
        "selected_mechanism": selected,
        "recommendation": (
            "replicate_selected_non_oracle_target_before_any_10x10_contract"
            if selected is not None
            else "no_candidate_recovers_enough_oracle_gain_design_new_value_target"
        ),
        "raw_arms": raw,
    }
    result["result_hash"] = _digest(result)
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    args = parser.parse_args()
    result = run_m15(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
    )
    print(json.dumps({
        "milestone": result["milestone"],
        "status": result["status"],
        "selected_mechanism": result["selected_mechanism"],
        "result_hash": result["result_hash"],
    }, sort_keys=True))
    return 0 if result["execution_gate"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
