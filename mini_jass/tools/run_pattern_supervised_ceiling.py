#!/usr/bin/env python3
"""M24-P: supervised ceiling of the folded PatternEval architecture.

Saturation is decided on the development cohort.  The frozen test is read
exactly once, at the largest preregistered dose, and only after saturation.
This is an oracle-trained upper bound, never a candidate.
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

import torch  # noqa: E402
import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.model import model_hash, parameter_count  # noqa: E402
from mini_jass_lab.model_factory import build_model, model_descriptor  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    RESPONSE_METRICS,
    assert_pattern_value_model,
    digest,
    mean,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything, train_epoch  # noqa: E402

SCHEMA = "mini_jass.pattern_supervised_ceiling.v1"
PRIMARY_METRIC = "zero_regret_rate"
DEVELOPMENT_COHORTS = ("train", "development")


def build_recommendation(
    by_dose: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    ladder = sorted((int(value) for value in by_dose), key=int)
    curve = [
        float(by_dose[str(dose)]["development"][PRIMARY_METRIC])
        for dose in ladder
    ]
    last_step = curve[-1] - curve[-2]
    tolerance = float(gate["saturation_tolerance"])
    saturated = abs(last_step) <= tolerance
    return {
        "status": "PASS" if saturated else "CEILING_NOT_SATURATED",
        "finding": (
            "development_curve_saturated"
            if saturated
            else "largest_dose_still_changes_development_response"
        ),
        "primary_metric": PRIMARY_METRIC,
        "selection_cohort": "development",
        "dose_ladder": ladder,
        "development_by_dose": curve,
        "last_dose_step": last_step,
        "saturation_tolerance": tolerance,
        "frozen_test_may_be_read": saturated,
        "promotable": False,
        "next_step": (
            "read_frozen_test_once_at_largest_dose"
            if saturated
            else "extend_dose_ladder_without_reading_frozen_test"
        ),
    }


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M24-P":
        raise ValueError("unexpected M24-P schema")
    boundaries = config.get("boundaries", {})
    expected = {
        "oracle_is_the_training_signal": True,
        "promotable": False,
        "production_jass_changes_authorized": False,
        "direct_10x10_transfer_authorized": False,
    }
    if any(boundaries.get(key) is not value for key, value in expected.items()):
        raise ValueError("M24-P crossed or hid a scientific boundary")
    doses = [int(value) for value in config["dose_ladder"]]
    if doses != sorted(doses) or len(doses) < 2 or len(set(doses)) != len(doses):
        raise ValueError("M24-P dose ladder must be unique, sorted, and non-trivial")
    if len(config.get("seeds", [])) < 2:
        raise ValueError("M24-P requires at least two seeds")
    if config["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M24-P must measure PatternEval")
    if float(config["training"]["policy_weight"]) != 0.0:
        raise ValueError("M24-P cannot train a policy head")
    return deepcopy(config)


def _fit(
    oracle,
    graph: GameGraph,
    tensors: dict[str, torch.Tensor],
    cohorts: dict[str, Any],
    config: dict[str, Any],
    epochs: int,
    seed: int,
):
    training = config["training"]
    seed_everything(seed, int(training["threads"]))
    model = build_model(config["model"])
    assert_pattern_value_model(model)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )
    for epoch in range(1, epochs + 1):
        train_epoch(
            model,
            optimizer,
            tensors,
            cohorts["train"],
            int(training["batch_size"]),
            seed + epoch * 7_919,
            float(training["value_weight"]),
            0.0,
        )
    metrics = {
        name: response_metrics(
            model,
            graph,
            tensors,
            oracle,
            cohorts[name],
            int(training["batch_size"]),
        )
        for name in DEVELOPMENT_COHORTS
    }
    return model, metrics


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        cohort: {
            key: mean(float(run[cohort][key]) for run in runs)
            for key in RESPONSE_METRICS
        }
        | {
            "count": int(runs[0][cohort]["count"]),
            "playable_count": int(runs[0][cohort]["playable_count"]),
            "action_source": "search_one_ply",
        }
        for cohort in DEVELOPMENT_COHORTS
    }


def run_m24p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M24-P requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(config["split_seed"]))
    if split.manifest["manifest_hash"] != config["expected_split_manifest_hash"]:
        raise ValueError("M24-P split differs from the frozen L1 contract")
    cohorts = {name: split.indices(name) for name in ("train", "development", "frozen_test")}
    tensors = solved_tensors(oracle, graph)

    by_dose: dict[str, Any] = {}
    top_models = []
    top = int(config["dose_ladder"][-1])
    for dose in config["dose_ladder"]:
        fitted = [
            _fit(oracle, graph, tensors, cohorts, config, int(dose), int(seed))
            for seed in config["seeds"]
        ]
        models = [item[0] for item in fitted]
        runs = [item[1] for item in fitted]
        by_dose[str(int(dose))] = _aggregate(runs) | {
            "seed_count": len(runs),
            "model_hashes": [model_hash(model) for model in models],
        }
        if int(dose) == top:
            top_models = models

    recommendation = build_recommendation(by_dose, config["scientific_gate"])
    frozen = None
    frozen_reads = 0
    if recommendation["frozen_test_may_be_read"]:
        rows = [
            response_metrics(
                model,
                graph,
                tensors,
                oracle,
                cohorts["frozen_test"],
                int(config["training"]["batch_size"]),
            )
            for model in top_models
        ]
        frozen_reads = len(rows)
        frozen = {
            key: mean(float(row[key]) for row in rows) for key in RESPONSE_METRICS
        } | {
            "count": int(rows[0]["count"]),
            "playable_count": int(rows[0]["playable_count"]),
            "action_source": "search_one_ply",
            "dose_epochs": top,
            "seed_count": len(rows),
        }
        recommendation["ceiling_primary_frozen_test"] = frozen[PRIMARY_METRIC]
        recommendation["distance_to_oracle_response"] = 1.0 - frozen[PRIMARY_METRIC]

    probe = build_model(config["model"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M24-P",
        "model": config["model"],
        "model_descriptor": model_descriptor(probe),
        "training": config["training"],
        "dose_ladder": config["dose_ladder"],
        "seeds": config["seeds"],
        "response_contract": "one_ply_value_search",
        "selection_cohort": "development",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result = {
        "schema": SCHEMA,
        "milestone": "M24-P",
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "parameter_count": parameter_count(probe),
        "aggregate": {"by_dose": by_dose, "frozen_test_at_selected_dose": frozen},
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "selection_uses_frozen_test": False,
            "frozen_test_reads": frozen_reads,
            "read_condition": "development_saturation_passed",
            "read_dose": top if frozen is not None else None,
        },
        "promotable": False,
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
    result = run_m24p(
        args.config, args.oracle, args.run_dir, args.compact_output, args.execution_host
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
