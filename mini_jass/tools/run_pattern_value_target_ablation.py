#!/usr/bin/env python3
"""M14-P: paired value-target ablation on one immutable PatternEval replay.

Both arms generate the same trajectories from the same initial model.  Only
the value labels consumed by ``train_from_replay`` differ.  The oracle arm is
diagnostic and can never be promoted.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.loop import execute_loop  # noqa: E402
from mini_jass_lab.model_factory import build_model, model_descriptor  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    assert_pattern_value_model,
    digest,
    mean,
    paired_interval,
    replay_fingerprint,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

SCHEMA = "mini_jass.pattern_value_target_ablation.v1"


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M14-P":
        raise ValueError("unexpected M14-P schema")
    if len(config.get("paired_seeds", [])) < 2:
        raise ValueError("M14-P requires paired seeds")
    if config.get("primary_contrast") != "exact_oracle_minus_selfplay_outcome":
        raise ValueError("M14-P primary contrast changed")
    if config.get("promotion_policy") != "oracle_arm_never_promotable":
        raise ValueError("M14-P oracle arm must remain diagnostic")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("cohorts_read") != ["development"]
        or boundaries.get("cohorts_sealed") != ["frozen_test"]
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M14-P crossed a scientific boundary")
    return deepcopy(config)


def _base_loop(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = config_path.resolve().parent.parent
    path = root / config["base_loop_config"]
    loop = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M14-P base loop has an unexpected schema")
    if int(loop["generations"]) != 1:
        raise ValueError("M14-P isolates labels on exactly one generation")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M14-P base loop must use PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M14-P cannot train a policy head")
    return loop


def _candidate(loop: dict[str, Any], state: dict[str, Any]):
    model = build_model(loop["model"])
    assert_pattern_value_model(model)
    model.load_state_dict(state)
    return model


def run_m14p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M14-P requires cpx62, got {host}")
    base_loop = _base_loop(config_path, config)
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M14-P split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    tensors = solved_tensors(oracle, graph)
    batch = int(base_loop["development"]["batch_size"])

    rows: list[dict[str, Any]] = []
    for raw_seed in config["paired_seeds"]:
        seed = int(raw_seed)
        loop = deepcopy(base_loop)
        loop["seed"] = seed
        baseline = execute_loop(
            loop,
            oracle,
            development,
            train,
            train_mask,
            value_target_source="selfplay_outcome",
        )
        exact = execute_loop(
            loop,
            oracle,
            development,
            train,
            train_mask,
            value_target_source="exact_oracle",
        )
        baseline_replay = replay_fingerprint(baseline.samples)
        exact_replay = replay_fingerprint(exact.samples)
        if baseline_replay != exact_replay:
            raise RuntimeError("M14-P arms did not generate the same immutable replay")

        seed_everything(seed, int(loop["runtime"]["threads"]))
        initial = build_model(loop["model"])
        assert_pattern_value_model(initial)
        before = response_metrics(
            initial, graph, tensors, oracle, development, batch
        )
        baseline_model = _candidate(loop, baseline.candidate_states[0])
        exact_model = _candidate(loop, exact.candidate_states[0])
        baseline_after = response_metrics(
            baseline_model, graph, tensors, oracle, development, batch
        )
        exact_after = response_metrics(
            exact_model, graph, tensors, oracle, development, batch
        )
        baseline_response_gain = (
            float(baseline_after["zero_regret_rate"])
            - float(before["zero_regret_rate"])
        )
        exact_response_gain = (
            float(exact_after["zero_regret_rate"])
            - float(before["zero_regret_rate"])
        )
        baseline_value_gain = (
            float(baseline_after["value_sign_accuracy"])
            - float(before["value_sign_accuracy"])
        )
        exact_value_gain = (
            float(exact_after["value_sign_accuracy"])
            - float(before["value_sign_accuracy"])
        )
        generated_ids = np.asarray(
            [sample.state_id for sample in baseline.samples], dtype=np.int64
        )
        generated_values = np.asarray(
            [sample.value_target for sample in baseline.samples], dtype=np.float32
        )
        target_exact_rate = float(
            np.mean(generated_values == oracle.values[generated_ids])
        )
        rows.append(
            {
                "seed": seed,
                "replay_fingerprint": baseline_replay,
                "replay_sample_count": len(baseline.samples),
                "generated_target_exact_rate": target_exact_rate,
                "initial": before,
                "baseline": {
                    "after": baseline_after,
                    "zero_regret_gain": baseline_response_gain,
                    "value_sign_gain": baseline_value_gain,
                },
                "exact_oracle": {
                    "after": exact_after,
                    "zero_regret_gain": exact_response_gain,
                    "value_sign_gain": exact_value_gain,
                    "training_relabel": exact.core["value_target_relabel"],
                },
                "contrast": {
                    "zero_regret_gain": exact_response_gain - baseline_response_gain,
                    "value_sign_gain": exact_value_gain - baseline_value_gain,
                },
            }
        )

    response_ci = paired_interval(
        row["contrast"]["zero_regret_gain"] for row in rows
    )
    value_ci = paired_interval(row["contrast"]["value_sign_gain"] for row in rows)
    minimum = float(config["scientific_gate"]["minimum_response_gain"])
    supports_noise = response_ci["lower"] > minimum
    protocol = {
        "schema": SCHEMA,
        "milestone": "M14-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "primary_contrast": config["primary_contrast"],
        "single_factor": "value_target_source",
        "immutable_replay_required": True,
        "response_contract": "one_ply_value_search",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result = {
        "schema": SCHEMA,
        "milestone": "M14-P",
        "status": "PASS",
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": {
            "paired_seed_count": len(rows),
            "mean_generated_target_exact_rate": mean(
                row["generated_target_exact_rate"] for row in rows
            ),
            "zero_regret_gain_exact_minus_outcome": response_ci,
            "value_sign_gain_exact_minus_outcome": value_ci,
        },
        "seed_results": rows,
        "recommendation": {
            "finding": (
                "value_target_noise_limits_pattern_learning"
                if supports_noise
                else "value_target_noise_not_established_as_primary_limit"
            ),
            "supports_value_target_noise_hypothesis": supports_noise,
            "minimum_response_gain": minimum,
            "promotable": False,
        },
        "sealed_cohort_contract": {
            "cohorts_read": ["development"],
            "cohorts_not_read": ["frozen_test"],
        },
    }
    result["result_hash"] = digest(result)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
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
    result = run_m14p(
        args.config, args.oracle, args.run_dir, args.compact_output, args.execution_host
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
