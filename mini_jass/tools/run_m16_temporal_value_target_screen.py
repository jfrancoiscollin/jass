#!/usr/bin/env python3
"""M16: screen temporal non-oracle value targets after the M15 blend shortfall.

M14 proved that exact value labels restore L2 value learning. M15 then showed
that the same-state bounded-search score is useful but underpowered: the 50/50
outcome/search blend recovered 41.8% of the oracle gain, below the frozen 50%
screen.

M16 keeps the frozen M13/M14/M15 twenty seeds, positions, search traces, policy
targets, optimizer and evaluation cohorts fixed. It changes only the scalar
VALUE label consumed by training:

- selfplay_outcome: honest baseline;
- next_search: one-step bootstrap, -V_search(s[t+1]);
- lambda_50: temporal lambda-return with lambda=0.50;
- lambda_80: temporal lambda-return with lambda=0.80;
- exact_oracle: diagnostic upper bound, never promotable.

There are no intermediate rewards in Mini-Jass. For a non-terminal successor,
the score is negated because the side to move changes. The final sample of each
game falls back to its honest terminal outcome. With lambda=1 the recurrence
would reduce to the terminal outcome; with lambda=0 it is the one-step target.
The frozen L2 loop has one generation, so target construction cannot feed back
into the generated trajectory or search trace for a paired seed.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
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


SCHEMA = "mini_jass.m16_temporal_value_target_screen.v1"
M15_EVIDENCE_SCHEMA = "mini_jass.m15_search_value_target_screen.readout.v1"
EXPECTED_SEEDS = list(range(132001, 132021))
EXPECTED_ARMS = {
    "baseline": {"value_target_source": "selfplay_outcome"},
    "next_search": {
        "value_target_source": "temporal_lambda_return",
        "lambda": 0.0,
    },
    "lambda_50": {
        "value_target_source": "temporal_lambda_return",
        "lambda": 0.5,
    },
    "lambda_80": {
        "value_target_source": "temporal_lambda_return",
        "lambda": 0.8,
    },
    "oracle": {"value_target_source": "exact_oracle"},
}
CANDIDATE_ARMS = ("next_search", "lambda_50", "lambda_80")


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_mini_jass_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = config_path.parent.parent / path
    return path.resolve()


def _load_m15_evidence(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_mini_jass_path(config_path, str(config["m15_evidence"]))
    if _file_sha256(path) != config.get("expected_m15_evidence_sha256"):
        raise ValueError("M16 M15 evidence file hash changed")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if (
        evidence.get("schema") != M15_EVIDENCE_SCHEMA
        or evidence.get("milestone") != "M15"
        or evidence.get("result_hash") != config.get("expected_m15_result_hash")
        or evidence.get("status") != "FAIL"
        or evidence.get("selected_mechanism") is not None
    ):
        raise ValueError("M16 requires the exact retained M15 screen failure")
    candidates = evidence.get("candidates", {})
    if set(candidates) != {"search", "blend"}:
        raise ValueError("M16 M15 evidence candidate set changed")
    if any(bool(row.get("scientific_pass")) for row in candidates.values()):
        raise ValueError("M16 requires M15 to have selected no candidate")
    blend_recovery = float(candidates["blend"]["oracle_gain_recovery_fraction"])
    search_recovery = float(candidates["search"]["oracle_gain_recovery_fraction"])
    if not (0.0 < search_recovery < blend_recovery < 0.50):
        raise ValueError("M16 requires the retained M15 blend shortfall")
    contracts = evidence.get("contracts", {})
    if (
        contracts.get("m15_arms_promotable") is not False
        or contracts.get("production_jass_changes_authorized") is not False
        or contracts.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M16 M15 evidence crossed a forbidden boundary")
    evidence["_sha256"] = _file_sha256(path)
    return evidence


def _resolve_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M16":
        raise ValueError("unexpected M16 temporal-target schema")
    if config.get("expected_execution_host") != "cpx62":
        raise ValueError("M16 must remain cpx62-routed")
    if config.get("paired_seeds") != EXPECTED_SEEDS:
        raise ValueError("M16 must reuse the exact M13/M14/M15 twenty seeds")
    if config.get("arms") != EXPECTED_ARMS:
        raise ValueError("M16 arm definitions changed")
    if config.get("oracle_role") != "diagnostic_upper_bound_only":
        raise ValueError("M16 oracle arm must remain diagnostic-only")
    if config.get("promotion_policy") != "no_m16_arm_promotable":
        raise ValueError("M16 is a screen, not a promotion gate")

    contracts = config.get("contracts", {})
    expected_contracts = {
        "same_generated_positions_per_seed": True,
        "same_search_trace_per_seed": True,
        "same_policy_targets_per_seed": True,
        "successor_search_score_reprojected_to_current_stm": True,
        "terminal_fallback_uses_selfplay_outcome": True,
        "one_generation_only": True,
        "temporal_targets_use_oracle": False,
        "production_jass_changes_authorized": False,
        "direct_10x10_transfer_authorized": False,
    }
    if contracts != expected_contracts:
        raise ValueError("M16 contracts changed")

    base = (path.parent / str(config["base_replication_config"])).resolve()
    resolved_m13 = m13.resolve_seed_variance_replication_config(base)
    if resolved_m13["paired_seeds"] != EXPECTED_SEEDS:
        raise ValueError("M16/M13 paired seeds diverged")
    if int(resolved_m13["m12_resolved"]["loop"]["generations"]) != 1:
        raise ValueError("M16 target isolation requires exactly one generation")

    evidence = _load_m15_evidence(path, config)
    resolved = dict(config)
    resolved["base_replication_config"] = str(base)
    resolved["m15_evidence_resolved"] = evidence
    return resolved


def _temporal_targeted_generation(
    original_generate: Callable[..., GenerationResult],
    lambda_value: float,
) -> Callable[..., GenerationResult]:
    """Return a generator wrapper that changes only ReplaySample.value_target."""

    if not 0.0 <= lambda_value < 1.0:
        raise ValueError("M16 lambda must be in [0, 1)")

    def wrapped(*args: Any, **kwargs: Any) -> GenerationResult:
        generated = original_generate(*args, **kwargs)
        trace = generated.metrics.get("search_trace", [])
        root_scores: dict[tuple[int, int], float] = {}
        for row in trace:
            key = (int(row["game_id"]), int(row["ply"]))
            if key in root_scores:
                raise ValueError(f"M16 duplicate root score for {key}")
            root_scores[key] = float(row["root_score"])

        game_indices: dict[int, list[int]] = {}
        for index, sample in enumerate(generated.samples):
            game_indices.setdefault(int(sample.game_id), []).append(index)

        rebuilt = list(generated.samples)
        for game_id, indices in game_indices.items():
            ordered = sorted(indices, key=lambda index: int(generated.samples[index].ply))
            plies = [int(generated.samples[index].ply) for index in ordered]
            if plies != list(range(plies[0], plies[0] + len(plies))):
                raise ValueError(f"M16 requires contiguous per-ply samples for game {game_id}")
            for index in ordered:
                sample = generated.samples[index]
                key = (game_id, int(sample.ply))
                if key not in root_scores:
                    raise ValueError(f"M16 missing root score for generated sample {key}")

            returns = [0.0] * len(ordered)
            last_sample = generated.samples[ordered[-1]]
            returns[-1] = float(last_sample.value_target)
            for local_index in range(len(ordered) - 2, -1, -1):
                next_sample = generated.samples[ordered[local_index + 1]]
                next_key = (game_id, int(next_sample.ply))
                next_search = float(np.clip(root_scores[next_key], -1.0, 1.0))
                # Both next_search and returns[local_index + 1] are from the
                # successor side-to-move perspective. Negate their convex
                # combination to express the target from the current STM.
                returns[local_index] = -(
                    (1.0 - lambda_value) * next_search
                    + lambda_value * returns[local_index + 1]
                )

            for local_index, source_index in enumerate(ordered):
                rebuilt[source_index] = replace(
                    generated.samples[source_index],
                    value_target=float(returns[local_index]),
                )

        metrics = dict(generated.metrics)
        metrics["m16_value_target"] = {
            "source": "temporal_lambda_return",
            "lambda": float(lambda_value),
            "bootstrap": "negated_successor_root_score",
            "terminal_fallback": "selfplay_outcome",
            "uses_oracle": False,
            "sample_count": len(rebuilt),
            "game_count": len(game_indices),
        }
        return GenerationResult(
            samples=rebuilt,
            metrics=metrics,
            coverage=generated.coverage,
        )

    return wrapped


def _mark_temporal_execution(execution: Any, lambda_value: float) -> Any:
    """Make the execution contract and hash state the temporal target honestly."""

    core = execution.core
    core.pop("execution_hash", None)
    core["training_target_contract"]["value"] = "temporal_lambda_return"
    core["value_target_source"] = "temporal_lambda_return"
    core["temporal_value_target"] = {
        "lambda": float(lambda_value),
        "bootstrap": "negated_successor_root_score",
        "terminal_fallback": "selfplay_outcome",
        "uses_oracle": False,
        "promotable": False,
    }
    core["execution_hash"] = _digest(core)
    return execution


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
                if "value_target_source" in kwargs:
                    raise ValueError("M16 owns the oracle target source")
                kwargs["value_target_source"] = "exact_oracle"
                return original_execute(*args, **kwargs)

            m13.execute_loop = execute_with_oracle
        elif source == "temporal_lambda_return":
            lambda_value = float(spec["lambda"])
            loop_module.generate_self_play = _temporal_targeted_generation(
                original_generate,
                lambda_value,
            )

            def execute_with_temporal(*args: Any, **kwargs: Any) -> Any:
                if "value_target_source" in kwargs:
                    raise ValueError("M16 owns the temporal target source")
                execution = original_execute(*args, **kwargs)
                return _mark_temporal_execution(execution, lambda_value)

            m13.execute_loop = execute_with_temporal
        elif source != "selfplay_outcome":
            raise ValueError(f"unknown M16 arm source: {source}")

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


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float], critical: float) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    if samples.size < 2:
        value = float(samples[0]) if samples.size else 0.0
        return [value, value]
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def _mean_target_value_mae(result: dict[str, Any]) -> float:
    return _mean([
        float(row["targets"]["value_mae"]) for row in result["seed_results"]
    ])


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
        "mean_target_value_exact_rate": float(
            aggregate["mean_target_value_exact_rate"]
        ),
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


def _paired_deltas(
    candidate: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, float | int]]:
    left = {int(row["seed"]): row for row in baseline["seed_results"]}
    right = {int(row["seed"]): row for row in candidate["seed_results"]}
    if sorted(left) != EXPECTED_SEEDS or sorted(right) != EXPECTED_SEEDS:
        raise ValueError("M16 arm results do not contain the same twenty seeds")
    rows: list[dict[str, float | int]] = []
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


def run_m16(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve_config(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M16 requires cpx62, got {host}")

    base_config = Path(config["base_replication_config"])
    run_dir.mkdir(parents=True, exist_ok=True)
    raw: dict[str, dict[str, Any]] = {}
    for arm in ("baseline", *CANDIDATE_ARMS, "oracle"):
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
    oracle_confirmation_gain = (
        float(oracle["mean_confirmation_value_sign_delta"])
        - float(baseline["mean_confirmation_value_sign_delta"])
    )
    oracle_development_gain = (
        float(oracle["mean_development_value_sign_delta"])
        - float(baseline["mean_development_value_sign_delta"])
    )
    if oracle_confirmation_gain <= 0.0 or oracle_development_gain <= 0.0:
        raise ValueError("M16 requires a positive paired oracle upper bound")

    rule = config["success_rule"]
    maximum_policy_shift = float(rule["maximum_absolute_policy_mass_delta"])
    minimum_recovery = float(rule["minimum_oracle_gain_recovery_fraction"])
    critical = float(rule["paired_confidence_critical_95"])
    m15_blend_recovery = float(
        config["m15_evidence_resolved"]["candidates"]["blend"][
            "oracle_gain_recovery_fraction"
        ]
    )

    feasible: dict[str, Any] = {}
    for arm in CANDIDATE_ARMS:
        contrast = _contrast(metrics[arm], baseline)
        paired = _paired_deltas(raw[arm], raw["baseline"])
        confirmation_ci = _confidence_95(
            [float(row["confirmation_value_sign_delta"]) for row in paired],
            critical,
        )
        development_ci = _confidence_95(
            [float(row["development_value_sign_delta"]) for row in paired],
            critical,
        )
        recovery = (
            contrast["mean_confirmation_value_sign_delta"]
            / oracle_confirmation_gain
        )
        criteria = {
            "all_twenty_runs_successful": (
                int(metrics[arm]["successful_run_count"]) == 20
            ),
            "confirmation_value_gain_positive": (
                contrast["mean_confirmation_value_sign_delta"] > 0.0
            ),
            "development_value_gain_positive": (
                contrast["mean_development_value_sign_delta"] > 0.0
            ),
            "confirmation_paired_ci95_above_zero": confirmation_ci[0] > 0.0,
            "development_paired_ci95_above_zero": development_ci[0] > 0.0,
            "minimum_oracle_gain_recovery": recovery >= minimum_recovery,
            "confirmation_policy_shift_within_limit": (
                abs(contrast["mean_confirmation_optimal_mass_delta"])
                <= maximum_policy_shift
            ),
            "development_policy_shift_within_limit": (
                abs(contrast["mean_development_optimal_mass_delta"])
                <= maximum_policy_shift
            ),
            "temporal_target_oracle_blind": True,
        }
        feasible[arm] = {
            "contrast_vs_baseline": contrast,
            "oracle_gain_recovery_fraction": float(recovery),
            "paired_confirmation_value_gain_confidence_95": confirmation_ci,
            "paired_development_value_gain_confidence_95": development_ci,
            "exceeds_m15_blend_recovery": recovery > m15_blend_recovery,
            "scientific_gate": {
                "status": "PASS" if all(criteria.values()) else "FAIL",
                "criteria": criteria,
            },
            "scientific_pass": all(criteria.values()),
            "paired_seed_deltas": paired,
        }

    execution_ok = all(
        result["execution_gate"]["status"] == "PASS"
        and result["pack"]["successful_run_count"] == 20
        for result in raw.values()
    )
    winners = [arm for arm in CANDIDATE_ARMS if feasible[arm]["scientific_pass"]]
    selected = max(
        winners,
        key=lambda arm: (
            float(feasible[arm]["oracle_gain_recovery_fraction"]),
            float(
                feasible[arm]["contrast_vs_baseline"][
                    "mean_confirmation_value_sign_delta"
                ]
            ),
        ),
        default=None,
    )

    evidence = config["m15_evidence_resolved"]
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M16",
        "status": "PASS" if execution_ok and selected is not None else "FAIL",
        "execution_gate": {
            "status": "PASS" if execution_ok else "FAIL",
            "criteria": {
                "all_five_arms_completed": execution_ok,
                "same_twenty_paired_seeds": True,
                "one_generation_prevents_target_feedback_into_trajectory": True,
                "successor_scores_reprojected_across_turn": True,
                "cpx62_execution_proven": host == "cpx62",
            },
        },
        "entry_evidence": {
            "m15_evidence_path": str(config["m15_evidence"]),
            "m15_evidence_sha256": evidence["_sha256"],
            "m15_result_hash": evidence["result_hash"],
            "m15_status": evidence["status"],
            "m15_selected_mechanism": evidence["selected_mechanism"],
            "m15_blend_oracle_gain_recovery_fraction": m15_blend_recovery,
        },
        "contracts": {
            "execution_host": host,
            "only_intended_factor": "value_target_consumed_by_training",
            "temporal_targets_use_oracle": False,
            "temporal_bootstrap_source": "successor_bounded_search_root_score",
            "terminal_fallback": "selfplay_outcome",
            "oracle_arm_diagnostic_only": True,
            "m16_arms_promotable": False,
            "production_jass_changes_authorized": False,
            "direct_10x10_transfer_authorized": False,
        },
        "oracle_upper_bound_gain": {
            "confirmation_value_sign": oracle_confirmation_gain,
            "development_value_sign": oracle_development_gain,
        },
        "arm_metrics": metrics,
        "feasible_target_results": feasible,
        "selected_mechanism": selected,
        "recommendation": (
            "replicate_selected_temporal_target_on_fresh_seeds_before_any_10x10_contract"
            if selected is not None
            else "no_temporal_candidate_recovers_half_oracle_gain_test_calibration_or_reanalysis"
        ),
        "raw_arms": raw,
    }
    result["result_hash"] = _digest(result)
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
    result = run_m16(
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
