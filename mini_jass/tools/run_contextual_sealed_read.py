#!/usr/bin/env python3
"""Read the contextual frozen_test cohort once, descriptively, for both C2 arms."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.context_replay import (  # noqa: E402
    allocate_disjoint_state_manifests,
    assigned_states,
)
from mini_jass_lab.context_training import tensor_state_hash  # noqa: E402
from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_eval import PatternEval  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    digest,
    mean,
    paired_interval,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.patterns import PatternSet  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from run_contextual_c1 import _scaffold, _write_json  # noqa: E402
from run_contextual_c2 import _resolve as _resolve_c2_contract  # noqa: E402

SCHEMA = "mini_jass.contextual_sealed_read.v1"
ARMS = ("WDL_ONLY", "WDL_PLUS_FULL_CONTEXT")
PRIMARY_HIGH = ARMS[1]
PRIMARY_LOW = ARMS[0]
C2_RESULT_HASH = "5bce01343ca2385485484ba6f46b7c0cf8c9d7bedc857010e9762de63abff9bd"
C2_FREEZE_HASH = "b9cd48bf1469aa53765a3cf8fee5419b83ad772a3c42972b6c39d29f51a306eb"


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config, base_loop = _resolve_c2_contract(path)
    if config.get("status") != "C2_FROZEN_SEALED_READ_implementation_ready_for_verification":
        raise ValueError("sealed read requires independently frozen C2 evidence")
    frozen = config["c2_disjoint_replication"]["frozen_report_v1"]
    if (
        frozen.get("source_result_hash") != C2_RESULT_HASH
        or frozen.get("freeze_report_hash") != C2_FREEZE_HASH
        or frozen.get("source_status")
        != "C2_COMPLETE_REJECTED_COMBINED_EFFECT_NONPOSITIVE"
        or frozen.get("freeze_status")
        != "PASS_C2_FREEZE_CHAINED_DECISION_FROZEN"
        or frozen.get("sealed_test_read") is not False
        or frozen.get("sealed_test_read_authorized") is not True
        or frozen.get("promotable") is not False
    ):
        raise ValueError("sealed read authorization differs from frozen C2")
    sealed = config["sealed_test_read"]
    execution = sealed["execution_v1"]
    arena = execution["common_search_arena"]
    if (
        tuple(sealed["arms_read_together"]) != ARMS
        or sealed.get("all_paired_seeds_read_together") is not True
        or sealed.get("may_select_model") is not False
        or execution.get("cohort") != "frozen_test"
        or execution.get("one_read_only") is not True
        or execution.get("no_training") is not True
        or execution.get("no_decision_reopening") is not True
        or execution.get("descriptive_only") is not True
        or arena.get("comparison")
        != "per_arm_minus_initial_shared_scaffold_export"
        or arena.get("reported_contrast")
        != "WDL_PLUS_FULL_CONTEXT_minus_WDL_ONLY"
        or arena.get("start_state_source") != "frozen_test_provided_unique"
        or int(arena["pairs_per_seed"]) != 64
    ):
        raise ValueError("sealed descriptive execution contract changed")
    return config, base_loop


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_embedded_hash(value: Mapping[str, Any], field: str) -> None:
    if digest({key: item for key, item in value.items() if key != field}) != value[field]:
        raise ValueError(f"{field} content hash mismatch")


def _verify_sources(
    config: Mapping[str, Any], result_path: Path, freeze_path: Path
) -> dict[str, Any]:
    frozen = config["c2_disjoint_replication"]["frozen_report_v1"]
    result = _load_json(result_path)
    freeze = _load_json(freeze_path)
    _verify_embedded_hash(freeze, "report_hash")
    if (
        freeze.get("schema") != "mini_jass.contextual_c2_freeze.v1"
        or freeze.get("report_hash") != frozen["freeze_report_hash"]
        or freeze.get("status") != frozen["freeze_status"]
        or freeze.get("source_result_hash") != frozen["source_result_hash"]
        or freeze.get("source_protocol_hash") != frozen["source_protocol_hash"]
        or freeze.get("source_implementation_sha")
        != frozen["source_implementation_sha"]
        or freeze.get("sealed_test_read_authorized") is not True
        or freeze.get("sealed_test_read") is not False
    ):
        raise ValueError("C2 freeze report differs from the sealed-read pin")
    if (
        result.get("schema") != "mini_jass.contextual_c2.v1"
        or result.get("result_hash") != frozen["source_result_hash"]
        or result.get("protocol_hash") != frozen["source_protocol_hash"]
        or result.get("implementation_sha") != frozen["source_implementation_sha"]
        or result.get("status") != frozen["source_status"]
        or result["sealed_cohort_contract"].get("cohorts_not_read")
        != ["frozen_test"]
    ):
        raise ValueError("C2 result differs from the sealed-read pin")
    payload = {
        key: value
        for key, value in result.items()
        if key not in ("elapsed_seconds", "result_hash")
    }
    if digest(payload) != result["result_hash"] or digest(result["protocol"]) != result[
        "protocol_hash"
    ]:
        raise ValueError("C2 result/protocol content hash mismatch")
    return result


def _file_sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _load_checkpoint(path: Path, config: Mapping[str, Any]) -> PatternEval:
    scaffold = config["training_scaffold_v1"]
    model = PatternEval(
        PatternSet.from_window(int(scaffold["pattern_window"])),
        include_reversible_plies=bool(scaffold["include_reversible_plies"]),
    )
    with np.load(path, allow_pickle=False) as payload:
        if set(payload.files) != {
            "bucket_weight",
            "extra_weight",
            "bias",
            "bucket_class",
        }:
            raise ValueError(f"unexpected checkpoint payload: {path}")
        if not np.array_equal(
            payload["bucket_class"], model.bucket_class.detach().cpu().numpy()
        ):
            raise ValueError(f"checkpoint bucket folding changed: {path}")
        state = model.state_dict()
        state["bucket_weight"] = torch.from_numpy(
            np.asarray(payload["bucket_weight"], dtype=np.float32)
        )
        state["extra_weight"] = torch.from_numpy(
            np.asarray(payload["extra_weight"], dtype=np.float32)
        )
        state["bias"] = torch.from_numpy(np.asarray(payload["bias"], dtype=np.float32))
        model.load_state_dict(state)
    return model


def _metric_delta(rows: list[dict[str, Any]], metric: str) -> list[float]:
    return [
        float(row["arms"][PRIMARY_HIGH][metric])
        - float(row["arms"][PRIMARY_LOW][metric])
        for row in rows
    ]


def run_sealed_read(
    config_path: Path,
    oracle_path: Path,
    c2_result_path: Path,
    c2_freeze_path: Path,
    checkpoint_dir: Path,
    run_dir: Path,
    compact_output: Path,
    *,
    implementation_sha: str,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    if len(implementation_sha) != 40 or any(
        character not in "0123456789abcdef" for character in implementation_sha
    ):
        raise ValueError("sealed-read implementation SHA must be a full Git SHA")
    host = execution_host or platform.node()
    if host != "cpx62":
        raise ValueError(f"contextual sealed read requires cpx62, got {host}")
    c2_result = _verify_sources(config, c2_result_path, c2_freeze_path)
    seeds = tuple(
        int(seed) for seed in config["c2_disjoint_replication"]["paired_seeds"]
    )
    if [row["seed"] for row in c2_result["c2_seed_results"]] != list(seeds):
        raise ValueError("C2 checkpoint seed inventory changed")

    checkpoint_hashes: dict[str, dict[str, str]] = {}
    models: dict[int, dict[str, PatternEval]] = {}
    for seed, source_row in zip(seeds, c2_result["c2_seed_results"], strict=True):
        checkpoint_hashes[str(seed)] = {}
        models[seed] = {}
        for arm in ARMS:
            path = checkpoint_dir / str(seed) / f"{arm}.npz"
            if not path.is_file():
                raise ValueError(f"missing sealed checkpoint: {path}")
            model = _load_checkpoint(path, config)
            expected = source_row["arms"][arm]["training"]["final_export_hash"]
            if tensor_state_hash(model) != expected:
                raise ValueError(f"sealed checkpoint state hash mismatch: {seed}/{arm}")
            checkpoint_hashes[str(seed)][arm] = _file_sha(path)
            models[seed][arm] = model
    expected_files = {
        checkpoint_dir / str(seed) / f"{arm}.npz" for seed in seeds for arm in ARMS
    }
    actual_files = set(checkpoint_dir.rglob("*.npz"))
    if actual_files != expected_files:
        raise ValueError("sealed checkpoint archive contains an unexpected file set")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != config["data_contract"]["split_manifest_hash"]:
        raise ValueError("sealed read split differs from the frozen L1 contract")
    frozen = split.indices("frozen_test")
    frozen_nonterminal = [
        int(state) for state in frozen if graph.terminal_value(int(state)) is None
    ]
    execution = config["sealed_test_read"]["execution_v1"]
    arena_config = execution["common_search_arena"]
    start_manifest = allocate_disjoint_state_manifests(
        frozen_nonterminal,
        {"SEALED": seeds},
        states_per_seed=int(arena_config["pairs_per_seed"]),
        namespace=(
            f"{arena_config['start_manifest_namespace']}|"
            f"{split.manifest['manifest_hash']}|{C2_RESULT_HASH}|{C2_FREEZE_HASH}"
        ),
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "sealed-arena-start-manifest.json", start_manifest)
    protocol = {
        "schema": SCHEMA,
        "config_schema": config["schema"],
        "trained_c2_result_hash": C2_RESULT_HASH,
        "c2_freeze_report_hash": C2_FREEZE_HASH,
        "trained_model_implementation_sha": config["c2_disjoint_replication"][
            "frozen_report_v1"
        ]["source_implementation_sha"],
        "reader_implementation_sha": implementation_sha,
        "paired_seeds": list(seeds),
        "arms_read_together": list(ARMS),
        "checkpoint_file_hashes": checkpoint_hashes,
        "split_manifest_hash": split.manifest["manifest_hash"],
        "sealed_arena_start_manifest_hash": start_manifest["manifest_hash"],
        "execution": execution,
        "execution_host": host,
        "protocol_hash_frozen_before_metric_read": True,
    }
    protocol_hash = digest(protocol)
    _write_json(
        run_dir / "SEALED_READ_STARTED.json",
        {
            "schema": "mini_jass.contextual_sealed_read_marker.v1",
            "protocol_hash": protocol_hash,
            "sealed_test_read_count": 1,
            "arms_read_together": list(ARMS),
            "paired_seeds": list(seeds),
            "complete": False,
        },
    )

    tensors = solved_tensors(oracle, graph)
    batch_size = int(base_loop["development"]["batch_size"])
    arena = ArenaConfig(
        pairs=int(arena_config["pairs_per_seed"]),
        max_plies=int(arena_config["max_plies"]),
        search_depth=int(arena_config["search_depth"]),
        node_budget=int(arena_config["node_budget"]),
        epsilon=float(arena_config["epsilon"]),
        confidence_z=float(arena_config["confidence_z"]),
        confidence_unit=str(arena_config["confidence_unit"]),
        start_state_source="provided",
    )
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    for seed in seeds:
        starts = assigned_states(start_manifest, "SEALED", seed)
        initial = _scaffold(config, seed).export_pattern_eval()
        source_row = c2_result["c2_seed_results"][len(rows)]
        if tensor_state_hash(initial) != source_row["initial_scalar_hash"]:
            raise RuntimeError(f"sealed initial scalar hash mismatch: {seed}")
        arm_rows: dict[str, Any] = {}
        arena_start_hash: str | None = None
        for arm in ARMS:
            metrics = response_metrics(
                models[seed][arm], graph, tensors, oracle, frozen, batch_size
            )
            arena_result = run_arena(
                graph,
                models[seed][arm],
                initial,
                arena,
                seed + int(arena_config["seed_offset"]),
                starts,
            )
            if int(arena_result["unique_start_state_count"]) != int(arena.pairs):
                raise RuntimeError("sealed arena did not use unique paired starts")
            current_start_hash = digest(arena_result["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = current_start_hash
            elif arena_start_hash != current_start_hash:
                raise RuntimeError("sealed arm arena starts diverged")
            arm_rows[arm] = {
                **metrics,
                "arena_score_vs_initial": float(arena_result["score"]),
                "arena": arena_result,
                "checkpoint_file_hash": checkpoint_hashes[str(seed)][arm],
            }
        rows.append(
            {
                "seed": seed,
                "arms": arm_rows,
                "arena_start_hash": arena_start_hash,
                "arena_score_delta_FULL_minus_WDL": float(
                    arm_rows[PRIMARY_HIGH]["arena_score_vs_initial"]
                    - arm_rows[PRIMARY_LOW]["arena_score_vs_initial"]
                ),
            }
        )
        _write_json(run_dir / f"seed-{seed}.json", rows[-1])

    critical = float(execution["paired_interval_critical_95"])
    metric_names = tuple(execution["all_state_response_metrics"])
    aggregate = {
        "paired_seed_count": len(rows),
        "frozen_test_state_count": int(frozen.size),
        "primary_common_search_arena_score": paired_interval(
            (row["arena_score_delta_FULL_minus_WDL"] for row in rows), critical
        ),
        "paired_all_state_metric_deltas_FULL_minus_WDL": {
            metric: paired_interval(_metric_delta(rows, metric), critical)
            for metric in metric_names
        },
        "arms": {
            arm: {
                f"mean_{metric}": mean(row["arms"][arm][metric] for row in rows)
                for metric in metric_names
            }
            for arm in ARMS
        },
        "all_arms_read_together": True,
        "all_paired_seeds_read_together": True,
        "all_arena_starts_paired": True,
        "training_performed": False,
        "decision_reopened": False,
        "may_select_model": False,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "SEALED_TEST_DESCRIPTIVE_READ_COMPLETE",
        "protocol_hash": protocol_hash,
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "elapsed_seconds": float(time.monotonic() - started),
        "sealed_test_read_count": 1,
        "final_chained_decision_unchanged": config["c2_disjoint_replication"][
            "frozen_report_v1"
        ]["final_chained_decision"]["decision"],
        "descriptive_only": True,
        "promotable": False,
        "implementation_sha": implementation_sha,
    }
    result["result_hash"] = digest(
        {key: value for key, value in result.items() if key != "elapsed_seconds"}
    )
    _write_json(run_dir / "result.full.json", result)
    _write_json(
        run_dir / "SEALED_READ_COMPLETE.json",
        {
            "schema": "mini_jass.contextual_sealed_read_marker.v1",
            "protocol_hash": protocol_hash,
            "result_hash": result["result_hash"],
            "sealed_test_read_count": 1,
            "complete": True,
        },
    )
    compact = {
        "schema": SCHEMA,
        "status": result["status"],
        "implementation_sha": implementation_sha,
        "protocol_hash": protocol_hash,
        "result_hash": result["result_hash"],
        "aggregate": aggregate,
        "sealed_test_read_count": 1,
        "final_chained_decision_unchanged": result[
            "final_chained_decision_unchanged"
        ],
        "descriptive_only": True,
        "promotable": False,
    }
    _write_json(compact_output, compact)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--c2-result", type=Path, required=True)
    parser.add_argument("--c2-freeze-report", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    parser.add_argument("--implementation-sha", required=True)
    args = parser.parse_args()
    result = run_sealed_read(
        args.config,
        args.oracle,
        args.c2_result,
        args.c2_freeze_report,
        args.checkpoint_dir,
        args.run_dir,
        args.compact_output,
        implementation_sha=args.implementation_sha,
        execution_host=args.execution_host,
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
