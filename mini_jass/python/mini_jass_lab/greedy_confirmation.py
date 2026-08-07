"""M11: independent confirmation of the L2 greedy-behavior diagnosis."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
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
from .split import SplitDefinition, build_split
from .train import seed_everything
from .wdl_diagnosis import target_noise_diagnostics


ARM_NAMES = ("baseline_top2", "greedy_behavior")
FRESH_PAIRED_SEEDS = (112001, 112002, 112003, 112004, 112005)
HOLDOUT_ALGORITHM = "sha256_ordered_train_canonical_holdout_v1"


@dataclass(frozen=True)
class ConfirmationHoldout:
    state_ids: np.ndarray
    canonical_ids: np.ndarray
    manifest: dict[str, Any]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _resolve_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_path.parent.parent / path


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float]) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    if samples.size < 2:
        return [float(samples[0]), float(samples[0])]
    critical = 2.7764451051977987 if samples.size == 5 else 1.96
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def _stable_holdout_order(seed: int, solver_hash: int, canonical_id: int) -> bytes:
    payload = (
        f"mini_jass.confirmation_holdout.v1|{seed}|{solver_hash}|{canonical_id}"
    ).encode()
    return hashlib.sha256(payload).digest()


def _integer_sequence_hash(values: np.ndarray) -> str:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(f"{int(value)}\n".encode())
    return hasher.hexdigest()


def derive_confirmation_holdout(
    oracle: OracleArrays,
    split: SplitDefinition,
    seed: int,
    fraction: float,
) -> ConfirmationHoldout:
    """Derive a canonical-class holdout strictly inside historical L2 train."""
    if not 0.0 < fraction < 1.0:
        raise ValueError("confirmation holdout fraction must be in (0, 1)")
    canonical_count = int(oracle.manifest["canonical_state_count"])
    if split.canonical_assignments.shape != (canonical_count,):
        raise ValueError("split and oracle canonical counts differ")

    train_canonical = np.flatnonzero(split.canonical_assignments == 0)
    if train_canonical.size < 2:
        raise ValueError("confirmation requires at least two train canonical classes")
    solver_hash = int(oracle.manifest["solver_hash"])
    ordered = sorted(
        (int(value) for value in train_canonical),
        key=lambda canonical_id: _stable_holdout_order(
            seed, solver_hash, canonical_id
        ),
    )
    holdout_count = int(len(ordered) * fraction)
    if holdout_count < 1 or holdout_count >= len(ordered):
        raise ValueError("confirmation holdout size leaves an empty partition")
    canonical_ids = np.asarray(ordered[:holdout_count], dtype=np.int64)

    selected = np.zeros(canonical_count, dtype=np.bool_)
    selected[canonical_ids] = True
    raw_selected = selected[oracle.canonical_ids]
    if np.any(split.raw_assignments[raw_selected] != 0):
        raise RuntimeError("confirmation holdout escaped the historical train cohort")
    state_ids = np.flatnonzero(raw_selected & (oracle.terminal_status == 0)).astype(
        np.int64
    )
    if not state_ids.size:
        raise ValueError("confirmation holdout has no non-terminal starts")

    representatives = np.full(canonical_count, -1, dtype=np.int64)
    for raw_id, canonical_id in enumerate(oracle.canonical_ids):
        if representatives[int(canonical_id)] < 0:
            representatives[int(canonical_id)] = raw_id
    canonical_values = oracle.values[representatives[canonical_ids]]
    assignment_hasher = hashlib.sha256()
    held_out = set(int(value) for value in canonical_ids)
    for canonical_id in sorted(int(value) for value in train_canonical):
        cohort = "confirmation_holdout" if canonical_id in held_out else "remaining_train"
        assignment_hasher.update(f"{canonical_id}:{cohort}\n".encode())

    manifest: dict[str, Any] = {
        "schema": "mini_jass.confirmation_holdout.l2.v1",
        "algorithm": HOLDOUT_ALGORITHM,
        "seed": int(seed),
        "fraction": float(fraction),
        "source_cohort": "historical_train_only",
        "source_split_manifest_hash": split.manifest["manifest_hash"],
        "solver_hash": solver_hash,
        "train_canonical_count": int(train_canonical.size),
        "holdout_canonical_count": int(canonical_ids.size),
        "holdout_nonterminal_raw_count": int(state_ids.size),
        "holdout_canonical_value_counts": {
            str(value): int(np.sum(canonical_values == value)) for value in (-1, 0, 1)
        },
        "holdout_raw_value_counts": {
            str(value): int(np.sum(oracle.values[state_ids] == value))
            for value in (-1, 0, 1)
        },
        "assignment_hash": assignment_hasher.hexdigest(),
        "state_ids_hash": _integer_sequence_hash(state_ids),
    }
    manifest["manifest_hash"] = _digest(manifest)
    return ConfirmationHoldout(state_ids, canonical_ids, manifest)


def resolve_greedy_confirmation_config(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.greedy_confirmation.v1":
        raise ValueError("unexpected greedy-confirmation schema")
    seeds = tuple(int(seed) for seed in config["paired_seeds"])
    if seeds != FRESH_PAIRED_SEEDS:
        raise ValueError("M11 fresh paired seeds changed after preregistration")
    if tuple(config["arms"]) != ARM_NAMES:
        raise ValueError("M11 paired arms or order changed after preregistration")
    if "frozen_test" in json.dumps(config).lower():
        raise ValueError("M11 must not name or consume the M9 frozen-test cohort")
    if int(config["games_per_arm"]) != 256:
        raise ValueError("M11 requires the preregistered 256 games per arm")

    m10_path = _resolve_path(config_path, config["m10_evidence"])
    m10 = json.loads(m10_path.read_text(encoding="utf-8"))
    greedy_delta = m10.get("aggregate", {}).get("paired_exact_rate_deltas", {}).get(
        "greedy_behavior", {}
    )
    if (
        m10.get("schema") != "mini_jass.m10_wdl_diagnosis.v1"
        or m10.get("result_hash") != config["expected_m10_result_hash"]
        or m10.get("status") != "PASS"
        or m10.get("recommendation", {}).get("primary_arm") != "greedy_behavior"
        or m10.get("recommendation", {}).get("decision")
        != "confirm_exploration_outcome_noise_on_fresh_l2_holdout"
        or float(greedy_delta.get("confidence_95", [0.0])[0]) <= 0.0
    ):
        raise ValueError("M11 requires the exact positive M10 greedy diagnosis")

    loop_path = _resolve_path(config_path, config["loop_config"])
    loop = yaml.safe_load(loop_path.read_text(encoding="utf-8"))
    self_play = loop.get("self_play", {})
    if (
        loop.get("schema") != "mini_jass.selfplay.v1"
        or self_play.get("policy_target") != "score_softmax"
        or self_play.get("behavior_policy") != "search_scores"
        or self_play.get("root_allocation") != "balanced"
        or self_play.get("start_state_source") != "train_split"
        or self_play.get("exploration", {}).get("strategy") != "top_k_uniform"
        or int(self_play.get("exploration", {}).get("top_k", 0)) != 2
    ):
        raise ValueError("M11 baseline differs from the frozen M9 mechanism")
    if config["arms"]["baseline_top2"].get("overrides") != {}:
        raise ValueError("M11 baseline must remain unchanged")
    if config["arms"]["greedy_behavior"].get("overrides") != {
        "self_play.exploration.strategy": "greedy"
    }:
        raise ValueError("M11 greedy arm must change behavior only")

    resolved = deepcopy(config)
    resolved["paired_seeds"] = list(seeds)
    resolved["m10_evidence"] = str(m10_path.resolve())
    resolved["m10"] = m10
    resolved["loop_config"] = str(loop_path.resolve())
    resolved["loop"] = loop
    resolved["split_manifest"] = str(
        _resolve_path(config_path, config["split_manifest"]).resolve()
    )
    return resolved


def policy_target_diagnostics(
    samples: list[ReplaySample], oracle: OracleArrays
) -> dict[str, float]:
    if not samples:
        raise ValueError("policy diagnosis requires generated samples")
    masses: list[float] = []
    optimal_argmax = 0
    for sample in samples:
        optimal = oracle.optimal_mask[sample.state_id]
        masses.append(float(sample.policy_target[optimal].sum()))
        optimal_argmax += int(optimal[int(np.argmax(sample.policy_target))])
    return {
        "policy_optimal_mass": _mean(masses),
        "policy_optimal_argmax_rate": optimal_argmax / len(samples),
    }


def build_greedy_confirmation_recommendation(
    aggregate: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    delta = aggregate["paired_exact_rate_delta"]
    safety_delta = aggregate["paired_safety_draw_game_rate_delta"]
    greedy = aggregate["arms"]["greedy_behavior"]
    criteria = {
        "all_ten_runs_successful": aggregate["successful_run_count"] == 10,
        "paired_initial_weights": bool(aggregate["paired_initial_weights"]),
        "paired_start_sequences": bool(aggregate["paired_start_sequences"]),
        "historical_train_holdout_only": bool(
            aggregate["historical_train_holdout_only"]
        ),
        "m9_frozen_test_untouched": aggregate["m9_frozen_test_reads"] == 0,
        "minimum_greedy_exact_rate": greedy["mean_exact_rate"]
        >= float(thresholds["minimum_greedy_exact_rate"]),
        "minimum_mean_exact_rate_delta": delta["mean"]
        >= float(thresholds["minimum_mean_exact_rate_delta"]),
        "exact_rate_delta_confidence_above_zero": delta["confidence_95"][0] > 0.0,
        "minimum_greedy_policy_optimal_mass": greedy["mean_policy_optimal_mass"]
        >= float(thresholds["minimum_greedy_policy_optimal_mass"]),
        "maximum_safety_draw_rate_increase": safety_delta["mean"]
        <= float(thresholds["maximum_safety_draw_rate_increase"]),
    }
    passed = all(criteria.values())
    return {
        "decision": (
            "rerun_l2_replication_with_confirmed_greedy_behavior"
            if passed
            else "keep_l2_gate_closed"
        ),
        "exploration_outcome_noise_confirmed": passed,
        "l2_replication_rerun_authorized": passed,
        "l2_transfer_confirmed": False,
        "implementation_preparation_authorized": False,
        "direct_10x10_transfer_authorized": False,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "next_gate": (
            "Rerun the full L2 learning replication with greedy behavior on fresh train-derived data."
            if passed
            else "Redesign L2 outcome targets without reopening the M9 frozen cohort."
        ),
    }


def _start_sequence_hash(seed: int, games: int, state_ids: np.ndarray) -> str:
    selected = np.asarray(
        [
            int(np.random.default_rng(seed + 10_000 + game_id).choice(state_ids))
            for game_id in range(games)
        ],
        dtype=np.int64,
    )
    return _integer_sequence_hash(selected)


def run_greedy_confirmation(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_greedy_confirmation_config(config_path)
    oracle = load_oracle(oracle_path)
    if (
        oracle.manifest.get("schema") != "mini_jass.oracle_dataset.l2.v1"
        or oracle.state_count != 49690
        or oracle.action_count != 122
        or oracle.feature_count != 74
    ):
        raise ValueError("M11 requires the frozen selected-scope L2 oracle")
    split = build_split(oracle, int(resolved["split_seed"]))
    frozen_split = json.loads(
        Path(resolved["split_manifest"]).read_text(encoding="utf-8")
    )
    if split.manifest != frozen_split:
        raise ValueError("M11 split differs from the frozen L2 contract")
    holdout = derive_confirmation_holdout(
        oracle,
        split,
        int(resolved["confirmation_holdout"]["seed"]),
        float(resolved["confirmation_holdout"]["fraction"]),
    )
    graph = GameGraph.from_oracle(oracle)
    graph.validate()

    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "games_per_arm": resolved["games_per_arm"],
        "arms": resolved["arms"],
        "baseline_loop": resolved["loop"],
        "confirmation_holdout": holdout.manifest,
        "scientific_gate": resolved["scientific_gate"],
        "evidence_scope": "historical_train_holdout_only",
        "forbidden_cohort": "m9_frozen_test",
        "m10_result_hash": resolved["expected_m10_result_hash"],
        "solver_hash": oracle.manifest["solver_hash"],
        "split_manifest_hash": split.manifest["manifest_hash"],
    }
    protocol_hash = _digest(protocol)
    rows: list[dict[str, Any]] = []
    games = int(resolved["games_per_arm"])

    for seed in resolved["paired_seeds"]:
        initial_hashes: dict[str, str] = {}
        expected_start_hash = _start_sequence_hash(seed, games, holdout.state_ids)
        for arm_name, arm in resolved["arms"].items():
            loop = deepcopy(resolved["loop"])
            loop["self_play"]["games"] = games
            _apply_overrides(loop, arm["overrides"])
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
                start_state_ids=holdout.state_ids,
            )
            diagnostics = target_noise_diagnostics(
                generated.samples,
                oracle,
                set(
                    int(value)
                    for value in generated.metrics["safety_draw_game_ids"]
                ),
            )
            diagnostics.update(policy_target_diagnostics(generated.samples, oracle))
            rows.append(
                {
                    "seed": seed,
                    "arm": arm_name,
                    "initial_model_hash": initial_hashes[arm_name],
                    "start_sequence_hash": expected_start_hash,
                    "self_play": {
                        "games": generated.metrics["games"],
                        "positions": generated.metrics["positions"],
                        "mean_game_length": generated.metrics["mean_game_length"],
                        "max_game_length": generated.metrics["max_game_length"],
                        "safety_draws": generated.metrics["safety_draws"],
                        "unique_start_states": generated.metrics["start_states"][
                            "unique"
                        ],
                    },
                    "diagnostics": diagnostics,
                }
            )
        if len(set(initial_hashes.values())) != 1:
            raise RuntimeError("M11 arms do not share paired initial weights")

    by_arm: dict[str, Any] = {}
    for arm_name in ARM_NAMES:
        selected = [row for row in rows if row["arm"] == arm_name]
        by_arm[arm_name] = {
            "run_count": len(selected),
            "mean_exact_rate": _mean(
                [float(row["diagnostics"]["exact_rate"]) for row in selected]
            ),
            "mean_policy_optimal_mass": _mean(
                [
                    float(row["diagnostics"]["policy_optimal_mass"])
                    for row in selected
                ]
            ),
            "mean_policy_optimal_argmax_rate": _mean(
                [
                    float(row["diagnostics"]["policy_optimal_argmax_rate"])
                    for row in selected
                ]
            ),
            "mean_safety_draw_game_rate": _mean(
                [
                    float(row["self_play"]["safety_draws"])
                    / float(row["self_play"]["games"])
                    for row in selected
                ]
            ),
            "mean_unique_states": _mean(
                [float(row["diagnostics"]["unique_states"]) for row in selected]
            ),
        }

    rows_by_arm = {
        arm_name: {
            int(row["seed"]): row for row in rows if row["arm"] == arm_name
        }
        for arm_name in ARM_NAMES
    }
    exact_deltas = [
        float(rows_by_arm["greedy_behavior"][seed]["diagnostics"]["exact_rate"])
        - float(rows_by_arm["baseline_top2"][seed]["diagnostics"]["exact_rate"])
        for seed in resolved["paired_seeds"]
    ]
    safety_deltas = [
        float(rows_by_arm["greedy_behavior"][seed]["self_play"]["safety_draws"])
        / games
        - float(rows_by_arm["baseline_top2"][seed]["self_play"]["safety_draws"])
        / games
        for seed in resolved["paired_seeds"]
    ]
    aggregate = {
        "run_count": len(rows),
        "successful_run_count": len(rows),
        "paired_initial_weights": True,
        "paired_start_sequences": all(
            rows_by_arm["baseline_top2"][seed]["start_sequence_hash"]
            == rows_by_arm["greedy_behavior"][seed]["start_sequence_hash"]
            for seed in resolved["paired_seeds"]
        ),
        "historical_train_holdout_only": True,
        "m9_frozen_test_reads": 0,
        "arms": by_arm,
        "paired_exact_rate_delta": {
            "mean": _mean(exact_deltas),
            "confidence_95": _confidence_95(exact_deltas),
            "by_seed": exact_deltas,
        },
        "paired_safety_draw_game_rate_delta": {
            "mean": _mean(safety_deltas),
            "confidence_95": _confidence_95(safety_deltas),
            "by_seed": safety_deltas,
        },
    }
    recommendation = build_greedy_confirmation_recommendation(
        aggregate, resolved["scientific_gate"]
    )
    result: dict[str, Any] = {
        "schema": "mini_jass.m11_greedy_confirmation.v1",
        "milestone": "M11",
        "status": recommendation["gate"]["status"],
        "protocol_hash": protocol_hash,
        "execution_gate": {
            "status": "PASS" if len(rows) == 10 else "FAIL",
            "criteria": {
                "all_ten_runs_successful": len(rows) == 10,
                "paired_initial_weights": True,
                "paired_start_sequences": aggregate["paired_start_sequences"],
                "historical_train_holdout_only": True,
                "m9_frozen_test_untouched": True,
            },
        },
        "scientific_gate": recommendation["gate"],
        "contracts": {
            "m10_result_hash": resolved["expected_m10_result_hash"],
            "m10_evidence_sha256": _file_sha256(Path(resolved["m10_evidence"])),
            "solver_hash": oracle.manifest["solver_hash"],
            "solver_manifest_hash": oracle.manifest["manifest_hash"],
            "split_manifest_hash": split.manifest["manifest_hash"],
            "confirmation_holdout_manifest_hash": holdout.manifest[
                "manifest_hash"
            ],
            "python_package_sha256": _package_sha256(),
            "jass_production_paths_modified": False,
        },
        "confirmation_holdout": holdout.manifest,
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
    (output_dir / "confirmation_holdout.json").write_bytes(
        _json_bytes(holdout.manifest)
    )
    (output_dir / "runs.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (output_dir / "result.json").write_bytes(_json_bytes(result))
    (output_dir / "environment.json").write_bytes(
        _json_bytes(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "numpy": np.__version__,
                "threads": resolved["loop"]["runtime"]["threads"],
            }
        )
    )
    compact = deepcopy(result)
    compact.pop("runs")
    if compact_output is not None:
        ensure_artefact_path(compact_output).write_bytes(_json_bytes(compact))
    return result
