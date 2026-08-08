#!/usr/bin/env python3
"""M14 diagnostic A/B: self-play outcome value targets vs exact-oracle targets.

The experiment deliberately reuses the frozen M13 protocol and paired seeds.
Only ``value_target_source`` is changed. The exact-oracle arm is diagnostic and
must never be treated as a promotable candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import mini_jass_lab.seed_variance_replication as m13  # noqa: E402


SCHEMA = "mini_jass.m14_value_target_ablation.v1"
EXPECTED_SEEDS = list(range(132001, 132021))
ALLOWED_SOURCES = {"selfplay_outcome", "exact_oracle"}


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M14":
        raise ValueError("unexpected M14 value-target ablation schema")
    if config.get("expected_execution_host") != "cpx62":
        raise ValueError("M14 must remain cpx62-routed")
    if config.get("paired_seeds") != EXPECTED_SEEDS:
        raise ValueError("M14 must reuse the exact 20 preregistered M13 seeds")
    if config.get("primary_contrast") != "exact_oracle_minus_selfplay_outcome":
        raise ValueError("M14 primary contrast changed")
    if config.get("promotion_policy") != "oracle_arm_never_promotable":
        raise ValueError("M14 oracle arm must remain diagnostic-only")
    arms = config.get("arms", {})
    expected_arms = {
        "baseline": {"value_target_source": "selfplay_outcome"},
        "oracle": {"value_target_source": "exact_oracle"},
    }
    if arms != expected_arms:
        raise ValueError("M14 arm definitions changed")
    for arm in arms.values():
        if arm["value_target_source"] not in ALLOWED_SOURCES:
            raise ValueError("unknown M14 value-target source")
    base = (path.parent / str(config["base_replication_config"])).resolve()
    resolved_m13 = m13.resolve_seed_variance_replication_config(base)
    if resolved_m13["paired_seeds"] != EXPECTED_SEEDS:
        raise ValueError("M14/M13 paired seeds diverged")
    resolved = dict(config)
    resolved["base_replication_config"] = str(base)
    return resolved


def _run_arm(
    *,
    source: str,
    base_config: Path,
    oracle: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str,
) -> dict[str, Any]:
    original_execute_loop = m13.execute_loop

    def execute_loop_with_target_source(*args: Any, **kwargs: Any) -> Any:
        if "value_target_source" in kwargs:
            raise ValueError("M14 owns value_target_source for the whole arm")
        kwargs["value_target_source"] = source
        return original_execute_loop(*args, **kwargs)

    m13.execute_loop = execute_loop_with_target_source
    try:
        return m13.run_seed_variance_replication(
            base_config,
            oracle,
            run_dir,
            compact_output,
            execution_host,
        )
    finally:
        m13.execute_loop = original_execute_loop


def _numeric_aggregate_delta(
    baseline: dict[str, Any], oracle: dict[str, Any]
) -> dict[str, float]:
    result: dict[str, float] = {}
    left = baseline["aggregate"]
    right = oracle["aggregate"]
    for key in sorted(set(left) & set(right)):
        a = left[key]
        b = right[key]
        if (
            isinstance(a, (int, float))
            and not isinstance(a, bool)
            and isinstance(b, (int, float))
            and not isinstance(b, bool)
        ):
            result[key] = float(b) - float(a)
    return result


def _paired_seed_deltas(
    baseline: dict[str, Any], oracle: dict[str, Any]
) -> list[dict[str, float | int]]:
    left = {int(row["seed"]): row for row in baseline["seed_results"]}
    right = {int(row["seed"]): row for row in oracle["seed_results"]}
    if sorted(left) != EXPECTED_SEEDS or sorted(right) != EXPECTED_SEEDS:
        raise ValueError("M14 arm results do not contain the same 20 seeds")
    rows: list[dict[str, float | int]] = []
    for seed in EXPECTED_SEEDS:
        rows.append(
            {
                "seed": seed,
                "development_value_sign_delta": float(
                    right[seed]["development"]["value_sign_delta"]
                    - left[seed]["development"]["value_sign_delta"]
                ),
                "development_optimal_mass_delta": float(
                    right[seed]["development"]["optimal_mass_delta"]
                    - left[seed]["development"]["optimal_mass_delta"]
                ),
                "confirmation_value_sign_delta": float(
                    right[seed]["confirmation"]["value_sign_delta"]
                    - left[seed]["confirmation"]["value_sign_delta"]
                ),
                "confirmation_optimal_mass_delta": float(
                    right[seed]["confirmation"]["optimal_mass_delta"]
                    - left[seed]["confirmation"]["optimal_mass_delta"]
                ),
                "target_value_exact_rate_delta": float(
                    right[seed]["targets"]["value_exact_rate"]
                    - left[seed]["targets"]["value_exact_rate"]
                ),
            }
        )
    return rows


def run_m14(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve_config(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M14 requires cpx62, got {host}")

    base_config = Path(config["base_replication_config"])
    run_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = run_dir / "baseline.m13.json"
    oracle_path_out = run_dir / "exact-oracle.m13.json"

    baseline = _run_arm(
        source="selfplay_outcome",
        base_config=base_config,
        oracle=oracle_path,
        run_dir=run_dir / "baseline",
        compact_output=baseline_path,
        execution_host=host,
    )
    oracle = _run_arm(
        source="exact_oracle",
        base_config=base_config,
        oracle=oracle_path,
        run_dir=run_dir / "exact-oracle",
        compact_output=oracle_path_out,
        execution_host=host,
    )

    execution_ok = (
        baseline["execution_gate"]["status"] == "PASS"
        and oracle["execution_gate"]["status"] == "PASS"
        and baseline["pack"]["successful_run_count"] == 20
        and oracle["pack"]["successful_run_count"] == 20
    )
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M14",
        "status": "PASS" if execution_ok else "FAIL",
        "execution_gate": {
            "status": "PASS" if execution_ok else "FAIL",
            "criteria": {
                "baseline_execution_passed": baseline["execution_gate"]["status"] == "PASS",
                "oracle_execution_passed": oracle["execution_gate"]["status"] == "PASS",
                "same_twenty_paired_seeds": True,
                "cpx62_execution_proven": host == "cpx62",
                "oracle_arm_diagnostic_only": True,
            },
        },
        "contracts": {
            "execution_host": host,
            "base_m13_protocol_hash_baseline": baseline["protocol_hash"],
            "base_m13_protocol_hash_oracle": oracle["protocol_hash"],
            "only_intended_factor": "value_target_source",
            "baseline_value_target_source": "selfplay_outcome",
            "oracle_value_target_source": "exact_oracle",
            "oracle_arm_promotable": False,
            "production_jass_changes_authorized": False,
            "direct_10x10_transfer_authorized": False,
        },
        "aggregate_delta_exact_oracle_minus_selfplay_outcome": _numeric_aggregate_delta(
            baseline, oracle
        ),
        "paired_seed_deltas": _paired_seed_deltas(baseline, oracle),
        "arms": {
            "baseline": baseline,
            "exact_oracle": oracle,
        },
        "interpretation_contract": {
            "positive_value_learning_delta_supports_value_target_noise_hypothesis": True,
            "null_or_negative_delta_points_away_from_value_target_noise_as_primary_cause": True,
            "oracle_arm_is_upper_bound_not_training_recipe": True,
        },
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
    result = run_m14(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["execution_gate"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
