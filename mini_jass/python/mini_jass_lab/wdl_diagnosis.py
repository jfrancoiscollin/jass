"""M10: causal diagnosis of noisy L2 self-play W/D/L targets."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np
import torch
import yaml

from .experiment import _apply_overrides, _digest, _file_sha256, _package_sha256
from .game_graph import GameGraph
from .loop import _parse_self_play
from .model import MiniJassMLP, ModelConfig, model_hash
from .oracle import OracleArrays, ensure_artefact_path, load_oracle
from .replay import ReplaySample
from .selfplay import generate_self_play
from .split import build_split
from .train import seed_everything


ARM_NAMES = ("baseline_64", "horizon_128", "budget_64", "greedy_behavior")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _resolve_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_path.parent.parent / path


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float]) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    critical = 2.7764451051977987 if samples.size == 5 else 1.96
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def resolve_wdl_diagnosis_config(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.wdl_diagnosis.v1":
        raise ValueError("unexpected W/D/L diagnosis schema")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 5 or len(set(seeds)) != 5:
        raise ValueError("M10 requires exactly five distinct paired seeds")
    if tuple(config["arms"]) != ARM_NAMES:
        raise ValueError("M10 causal arms or order changed after preregistration")
    if "frozen_test" in json.dumps(config).lower():
        raise ValueError("M10 must not name or consume the M9 frozen-test cohort")

    m9_path = _resolve_path(config_path, config["m9_evidence"])
    m9 = json.loads(m9_path.read_text(encoding="utf-8"))
    if (
        m9.get("schema") != "mini_jass.m9_l2_transfer_gate.v1"
        or m9.get("result_hash") != config["expected_m9_result_hash"]
        or m9.get("recommendation", {}).get("decision") != "keep_l2_gate_closed"
        or m9.get("scientific_gate", {}).get("criteria", {}).get(
            "minimum_target_value_exact_rate"
        ) is not False
    ):
        raise ValueError("M10 requires the exact closed M9 W/D/L gate")

    loop_path = _resolve_path(config_path, config["loop_config"])
    loop = yaml.safe_load(loop_path.read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M10 must reuse the stable L2 self-play interface")
    if (
        loop["self_play"].get("policy_target") != "score_softmax"
        or loop["self_play"].get("behavior_policy") != "search_scores"
        or loop["self_play"].get("root_allocation") != "balanced"
        or loop["self_play"].get("start_state_source") != "train_split"
    ):
        raise ValueError("M10 baseline differs from the frozen M9 mechanism")

    resolved = deepcopy(config)
    resolved["paired_seeds"] = seeds
    resolved["m9_evidence"] = str(m9_path.resolve())
    resolved["m9"] = m9
    resolved["loop_config"] = str(loop_path.resolve())
    resolved["loop"] = loop
    resolved["split_manifest"] = str(
        _resolve_path(config_path, config["split_manifest"]).resolve()
    )
    return resolved


def target_noise_diagnostics(
    samples: list[ReplaySample],
    oracle: OracleArrays,
    safety_draw_game_ids: set[int],
) -> dict[str, Any]:
    if not samples:
        raise ValueError("W/D/L diagnosis requires generated samples")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    targets = np.asarray([sample.value_target for sample in samples], dtype=np.int8)
    exact = oracle.values[state_ids].astype(np.int8)
    correct = targets == exact
    safety = np.asarray(
        [sample.game_id in safety_draw_game_ids for sample in samples], dtype=np.bool_
    )
    mismatch = ~correct

    matrix: dict[str, int] = {}
    for exact_value in (-1, 0, 1):
        for target_value in (-1, 0, 1):
            matrix[f"exact_{exact_value}_target_{target_value}"] = int(
                np.sum((exact == exact_value) & (targets == target_value))
            )

    dtw = oracle.dtw[state_ids]
    buckets = {
        "terminal_0": dtw == 0,
        "short_1_8": (dtw >= 1) & (dtw <= 8),
        "long_9_plus": dtw >= 9,
        "draw_no_dtw": dtw < 0,
    }
    by_dtw = {}
    for name, selected in buckets.items():
        count = int(selected.sum())
        by_dtw[name] = {
            "count": count,
            "exact_rate": float(correct[selected].mean()) if count else None,
        }

    mismatch_count = int(mismatch.sum())
    rule = ~safety
    return {
        "count": len(samples),
        "unique_states": int(np.unique(state_ids).size),
        "exact_rate": float(correct.mean()),
        "value_mae": float(np.abs(targets - exact).mean()),
        "safety_draw_sample_rate": float(safety.mean()),
        "safety_draw_exact_rate": float(correct[safety].mean()) if safety.any() else None,
        "rule_terminated_exact_rate": float(correct[rule].mean()) if rule.any() else None,
        "mismatch_count": mismatch_count,
        "mismatch_attributed_to_safety_draws": (
            float(np.sum(mismatch & safety) / mismatch_count) if mismatch_count else 0.0
        ),
        "mismatch_matrix": matrix,
        "by_dtw": by_dtw,
    }


def build_wdl_diagnosis_recommendation(
    aggregate: dict[str, Any], meaningful_delta: float
) -> dict[str, Any]:
    deltas = aggregate["paired_exact_rate_deltas"]
    eligible = {
        arm: values
        for arm, values in deltas.items()
        if float(values["mean"]) >= meaningful_delta
    }
    if eligible:
        primary = max(eligible, key=lambda arm: (eligible[arm]["mean"], arm))
        finding = {
            "horizon_128": "horizon_truncation",
            "budget_64": "insufficient_search_budget",
            "greedy_behavior": "exploration_outcome_noise",
        }[primary]
        decision = f"confirm_{finding}_on_fresh_l2_holdout"
    else:
        primary = None
        finding = "no_single_preregistered_factor_explains_wdl_noise"
        decision = "redesign_l2_value_targets_before_replication"
    return {
        "decision": decision,
        "primary_arm": primary,
        "finding": finding,
        "meaningful_delta": meaningful_delta,
        "l2_replication_authorized": False,
        "implementation_preparation_authorized": False,
        "direct_10x10_transfer_authorized": False,
        "next_gate": (
            "Confirm the identified factor with fresh seeds and a newly derived L2 holdout."
            if primary is not None
            else "Preregister a value-target redesign using fresh L2 data; never retune on M9 frozen data."
        ),
    }


def run_wdl_diagnosis(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_wdl_diagnosis_config(config_path)
    oracle = load_oracle(oracle_path)
    if (
        oracle.manifest.get("schema") != "mini_jass.oracle_dataset.l2.v1"
        or oracle.state_count != 49690
        or oracle.action_count != 122
    ):
        raise ValueError("M10 requires the frozen selected-scope L2 oracle")
    split = build_split(oracle, int(resolved["split_seed"]))
    frozen_split = json.loads(Path(resolved["split_manifest"]).read_text(encoding="utf-8"))
    if split.manifest != frozen_split:
        raise ValueError("M10 split differs from the frozen L2 contract")
    train_starts = np.asarray(
        [
            int(state_id)
            for state_id in split.indices("train")
            if int(oracle.terminal_status[int(state_id)]) == 0
        ],
        dtype=np.int64,
    )
    graph = GameGraph.from_oracle(oracle)
    graph.validate()

    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "arms": resolved["arms"],
        "baseline_loop": resolved["loop"],
        "meaningful_exact_rate_delta": resolved["meaningful_exact_rate_delta"],
        "cohort": "train_only",
        "forbidden_cohort": "m9_frozen_test",
        "m9_result_hash": resolved["expected_m9_result_hash"],
        "solver_hash": oracle.manifest["solver_hash"],
        "split_manifest_hash": split.manifest["manifest_hash"],
    }
    protocol_hash = _digest(protocol)
    rows: list[dict[str, Any]] = []

    for seed in resolved["paired_seeds"]:
        initial_hashes: dict[str, str] = {}
        for arm_name, arm in resolved["arms"].items():
            loop = deepcopy(resolved["loop"])
            _apply_overrides(loop, arm.get("overrides", {}))
            loop["seed"] = seed
            seed_everything(seed, int(loop["runtime"]["threads"]))
            model = MiniJassMLP(ModelConfig(**loop["model"]))
            initial_hashes[arm_name] = model_hash(model)
            generated = generate_self_play(
                graph,
                model,
                _parse_self_play(loop["self_play"]),
                generation=1,
                seed=seed + 10_000,
                start_state_ids=train_starts,
            )
            diagnostics = target_noise_diagnostics(
                generated.samples,
                oracle,
                set(int(value) for value in generated.metrics["safety_draw_game_ids"]),
            )
            rows.append({
                "seed": seed,
                "arm": arm_name,
                "initial_model_hash": initial_hashes[arm_name],
                "self_play": {
                    "games": generated.metrics["games"],
                    "positions": generated.metrics["positions"],
                    "mean_game_length": generated.metrics["mean_game_length"],
                    "max_game_length": generated.metrics["max_game_length"],
                    "safety_draws": generated.metrics["safety_draws"],
                    "unique_start_states": generated.metrics["start_states"]["unique"],
                },
                "diagnostics": diagnostics,
            })
        if len(set(initial_hashes.values())) != 1:
            raise RuntimeError("M10 arms do not share paired initial weights")

    by_arm: dict[str, Any] = {}
    for arm_name in ARM_NAMES:
        selected = [row for row in rows if row["arm"] == arm_name]
        by_arm[arm_name] = {
            "run_count": len(selected),
            "mean_exact_rate": _mean([
                float(row["diagnostics"]["exact_rate"]) for row in selected
            ]),
            "mean_rule_terminated_exact_rate": _mean([
                float(row["diagnostics"]["rule_terminated_exact_rate"]) for row in selected
            ]),
            "mean_safety_draw_game_rate": _mean([
                float(row["self_play"]["safety_draws"]) /
                float(row["self_play"]["games"]) for row in selected
            ]),
            "mean_mismatch_attributed_to_safety_draws": _mean([
                float(row["diagnostics"]["mismatch_attributed_to_safety_draws"])
                for row in selected
            ]),
            "mean_unique_states": _mean([
                float(row["diagnostics"]["unique_states"]) for row in selected
            ]),
        }

    baseline = {
        int(row["seed"]): float(row["diagnostics"]["exact_rate"])
        for row in rows if row["arm"] == "baseline_64"
    }
    paired_deltas = {}
    for arm_name in ARM_NAMES[1:]:
        arm_rows = {int(row["seed"]): row for row in rows if row["arm"] == arm_name}
        deltas = [
            float(arm_rows[seed]["diagnostics"]["exact_rate"]) - baseline[seed]
            for seed in resolved["paired_seeds"]
        ]
        paired_deltas[arm_name] = {
            "mean": _mean(deltas),
            "confidence_95": _confidence_95(deltas),
            "by_seed": deltas,
        }

    aggregate = {
        "run_count": len(rows),
        "successful_run_count": len(rows),
        "paired_initial_weights": True,
        "cohort": "train_only",
        "m9_frozen_test_reads": 0,
        "arms": by_arm,
        "paired_exact_rate_deltas": paired_deltas,
    }
    recommendation = build_wdl_diagnosis_recommendation(
        aggregate, float(resolved["meaningful_exact_rate_delta"])
    )
    result: dict[str, Any] = {
        "schema": "mini_jass.m10_wdl_diagnosis.v1",
        "milestone": "M10",
        "status": "PASS",
        "protocol_hash": protocol_hash,
        "execution_gate": {
            "status": "PASS",
            "criteria": {
                "all_twenty_runs_successful": len(rows) == 20,
                "paired_initial_weights": True,
                "train_cohort_only": True,
                "m9_frozen_test_untouched": True,
            },
        },
        "contracts": {
            "m9_result_hash": resolved["expected_m9_result_hash"],
            "m9_evidence_sha256": _file_sha256(Path(resolved["m9_evidence"])),
            "solver_hash": oracle.manifest["solver_hash"],
            "solver_manifest_hash": oracle.manifest["manifest_hash"],
            "split_manifest_hash": split.manifest["manifest_hash"],
            "python_package_sha256": _package_sha256(),
            "jass_production_paths_modified": False,
        },
        "aggregate": aggregate,
        "recommendation": recommendation,
        "runs": rows,
    }
    result["result_hash"] = _digest(result)

    output_dir = ensure_artefact_path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "protocol.json").write_bytes(_json_bytes(protocol))
    (output_dir / "runs.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (output_dir / "result.json").write_bytes(_json_bytes(result))
    (output_dir / "environment.json").write_bytes(_json_bytes({
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "threads": resolved["loop"]["runtime"]["threads"],
    }))
    compact = deepcopy(result)
    compact.pop("runs")
    if compact_output is not None:
        ensure_artefact_path(compact_output).write_bytes(_json_bytes(compact))
    return result
