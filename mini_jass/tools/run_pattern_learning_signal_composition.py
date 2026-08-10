#!/usr/bin/env python3
"""M21-P: test generation-mix strength on the deployable PatternEval path."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
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
from mini_jass_lab.replay import ReplaySample  # noqa: E402
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.selfplay_train import train_from_replay  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

SCHEMA = "mini_jass.pattern_learning_signal_composition.v1"
ARM_ORDER = (
    "G1_ONLY_OUTCOME",
    "G8_ONLY_OUTCOME",
    "MIX_OUTCOME",
    "G1_WIDE_OUTCOME",
    "G1_PLUS_NOVEL_LATE_OUTCOME",
    "G1_PLUS_MATCHED_LATE_OUTCOME",
)
CONTRASTS = {
    "generation_composition": ("MIX_OUTCOME", "G1_WIDE_OUTCOME"),
    "unique_sample_volume": ("G1_WIDE_OUTCOME", "G1_ONLY_OUTCOME"),
    "mix_total": ("MIX_OUTCOME", "G1_ONLY_OUTCOME"),
    "recency": ("G8_ONLY_OUTCOME", "G1_ONLY_OUTCOME"),
    "novel_late": ("G1_PLUS_NOVEL_LATE_OUTCOME", "G1_ONLY_OUTCOME"),
    "novelty_vs_matched": (
        "G1_PLUS_NOVEL_LATE_OUTCOME",
        "G1_PLUS_MATCHED_LATE_OUTCOME",
    ),
}
LATE_GENERATIONS = (5, 6, 7, 8)


def _arena_score_lower_bound(
    score: float, pairs: int, confidence_z: float, confidence_unit: str
) -> float:
    observations = 2 * pairs if confidence_unit == "games" else pairs
    standard_error = math.sqrt(max(score * (1.0 - score), 0.0) / observations)
    return max(0.0, score - confidence_z * standard_error)


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M21-P":
        raise ValueError("unexpected M21-P schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M21-P arms changed after preregistration")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 20 or len(set(seeds)) != 20:
        raise ValueError("M21-P requires 20 unique paired seeds")
    if set(seeds) & set(range(262001, 265021)):
        raise ValueError("M21-P must use fresh seeds after M17-P through M18-P")

    source = config.get("source_evidence", {})
    if (
        source.get("m17p2r_result_hash")
        != "c868949d2f1027889e6e76fd081e763aedcac7840f6105e1f18175e5c66685ea"
        or source.get("m18p_result_hash")
        != "2680f52319b7be31c5cb6d44c229b78c545eb21b4dc4c8be2e3f17c125da5554"
    ):
        raise ValueError("M21-P source evidence is not frozen")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("oracle_training_signal") is not False
        or boundaries.get("sample_selection_reads_oracle_labels") is not False
        or boundaries.get("cohorts_read") != ["train", "development"]
        or boundaries.get("cohorts_sealed") != ["frozen_test"]
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M21-P crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M21-P requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M21-P requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M21-P cannot train a policy head")
    if int(config["wide_games"]) != 8 * int(loop["self_play"]["games"]):
        raise ValueError("M21-P G1_WIDE must use eight times the G1 games")
    schedule = config["training_schedule"]
    if int(schedule["batch_size"]) != int(loop["training"]["batch_size"]):
        raise ValueError("M21-P batch size differs from the frozen recipe")

    promotion = config["promotion_control"]
    loop["arena"].update(
        {
            "pairs": int(promotion["arena_pairs"]),
            "epsilon": float(promotion["arena_epsilon"]),
            "start_state_source": "provided",
            "confidence_unit": str(promotion["arena_confidence_unit"]),
        }
    )
    if promotion["arena_start_state_source"] != "development":
        raise ValueError("M21-P promotion arena requires development starts")
    neutral_lower = _arena_score_lower_bound(
        0.5,
        int(loop["arena"]["pairs"]),
        float(loop["arena"]["confidence_z"]),
        str(loop["arena"]["confidence_unit"]),
    )
    if neutral_lower < float(loop["promotion"]["minimum_arena_lower_bound"]):
        raise ValueError("M21-P inherited an underpowered promotion arena")

    strength = config["strength_arena"]
    if (
        int(strength["pairs"]) < 1
        or float(strength["epsilon"]) != 0.0
        or strength["start_state_source"] != "development"
        or strength["confidence_unit"] != "pairs"
    ):
        raise ValueError("M21-P strength arena contract changed")
    gate = config["scientific_gate"]
    if (
        float(gate["minimum_practical_arena_gain"]) != 0.05
        or gate["require_ci_above_zero"] is not True
    ):
        raise ValueError("M21-P science gate changed after preregistration")
    loop["generations"] = 8
    return deepcopy(config), loop


def _take(
    samples: list[ReplaySample], count: int, rng: np.random.Generator
) -> list[ReplaySample]:
    if count > len(samples):
        raise ValueError(f"sample pool needs {count} rows, only {len(samples)} exist")
    indices = np.sort(rng.choice(len(samples), size=count, replace=False))
    return [samples[int(index)] for index in indices]


def _rng(seed: int, salt: int) -> np.random.Generator:
    return np.random.default_rng(seed * 1_000_003 + salt)


def coarse_strata(graph: GameGraph, state_ids: np.ndarray) -> np.ndarray:
    """Oracle-blind material/side/legal-count strata used by the matched arm."""
    planes = graph.features.shape[1] - 2
    per_plane = planes // 4
    board = graph.features[state_ids, :planes].reshape(len(state_ids), 4, per_plane)
    material = board.sum(axis=2).astype(np.int64)
    side = graph.features[state_ids, planes].astype(np.int64)
    legal = graph.legal_mask[state_ids].sum(axis=1).astype(np.int64)
    key = material[:, 0]
    for column in (material[:, 1], material[:, 2], material[:, 3], side, legal):
        key = key * 64 + column
    return key


def _sample_identity(source: str, sample: ReplaySample) -> dict[str, Any]:
    return {
        "source": source,
        "generation": int(sample.generation),
        "game_id": int(sample.game_id),
        "ply": int(sample.ply),
        "state_id": int(sample.state_id),
    }


def _identity_hash(source: str, samples: list[ReplaySample]) -> str:
    return digest([_sample_identity(source, sample) for sample in samples])


def build_pools(
    per_generation: dict[int, list[ReplaySample]],
    wide: list[ReplaySample],
    graph: GameGraph,
    seed: int,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    if set(per_generation) != set(range(1, 9)):
        raise ValueError("M21-P requires all eight generation pools")
    unit = min(len(per_generation[generation]) for generation in range(1, 9))
    if unit < 2:
        raise ValueError("M21-P needs at least two rows per generation")
    selected = {
        generation: _take(
            per_generation[generation], unit, _rng(seed, generation)
        )
        for generation in range(1, 9)
    }
    mix = [sample for generation in range(1, 9) for sample in selected[generation]]
    g1 = selected[1]
    g8 = selected[8]
    wide_selected = _take(wide, len(mix), _rng(seed, 404))

    late_count = unit // 2
    g1_count = unit - late_count
    g1_states = {int(sample.state_id) for sample in g1}
    late = [sample for generation in LATE_GENERATIONS for sample in selected[generation]]
    novel_candidates = [
        sample for sample in late if int(sample.state_id) not in g1_states
    ]
    if len(novel_candidates) < late_count:
        raise ValueError("M21-P has too few novel late-generation rows")
    novel = _take(novel_candidates, late_count, _rng(seed, 101))

    g1_keys = coarse_strata(
        graph, np.asarray([sample.state_id for sample in g1], dtype=np.int64)
    )
    late_keys = coarse_strata(
        graph, np.asarray([sample.state_id for sample in late], dtype=np.int64)
    )
    wanted, counts = np.unique(g1_keys, return_counts=True)
    target = counts / counts.sum()
    matched_rng = _rng(seed, 202)
    by_key: dict[int, list[int]] = {}
    for position, key in enumerate(late_keys):
        by_key.setdefault(int(key), []).append(position)
    matched: list[ReplaySample] = []
    used: set[int] = set()
    for choice in matched_rng.choice(
        len(wanted), size=late_count, replace=True, p=target
    ):
        key = int(wanted[int(choice)])
        candidates = [position for position in by_key.get(key, []) if position not in used]
        if not candidates:
            candidates = [position for position in range(len(late)) if position not in used]
        if not candidates:
            raise ValueError("M21-P matched-late pool exhausted")
        picked = int(matched_rng.choice(candidates))
        used.add(picked)
        matched.append(late[picked])

    g1_partial = _take(g1, g1_count, _rng(seed, 303))
    pools = {
        "G1_ONLY_OUTCOME": g1,
        "G8_ONLY_OUTCOME": g8,
        "MIX_OUTCOME": mix,
        "G1_WIDE_OUTCOME": wide_selected,
        "G1_PLUS_NOVEL_LATE_OUTCOME": g1_partial + novel,
        "G1_PLUS_MATCHED_LATE_OUTCOME": g1_partial + matched,
    }
    counts_by_arm = {arm: len(pool) for arm, pool in pools.items()}
    if counts_by_arm["MIX_OUTCOME"] != counts_by_arm["G1_WIDE_OUTCOME"]:
        raise RuntimeError("M21-P primary arms differ in unique-row count")
    unit_arms = [arm for arm in ARM_ORDER if arm not in {"MIX_OUTCOME", "G1_WIDE_OUTCOME"}]
    if any(counts_by_arm[arm] != unit for arm in unit_arms):
        raise RuntimeError("M21-P unit-dose controls differ in row count")
    return pools, {
        "unit_rows_per_generation": unit,
        "rows_by_arm": counts_by_arm,
        "unique_states_by_arm": {
            arm: len({int(sample.state_id) for sample in pool})
            for arm, pool in pools.items()
        },
        "identity_hash_by_arm": {
            arm: _identity_hash("wide" if arm == "G1_WIDE_OUTCOME" else "ladder", pool)
            for arm, pool in pools.items()
        },
        "novel_late_candidate_count": len(novel_candidates),
        "matched_late_drawn": len(matched),
        "matched_strata_dimensions": 3,
    }


def _random_schedule(
    pool_size: int, steps: int, batch_size: int, seed: int
) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        0, pool_size, size=(steps, batch_size), dtype=np.int64
    )


def _model_state_hash(model: Any) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        hasher.update(name.encode("utf-8"))
        hasher.update(tensor.detach().cpu().numpy().tobytes(order="C"))
    return hasher.hexdigest()


def _fit(
    loop: dict[str, Any],
    graph: GameGraph,
    samples: list[ReplaySample],
    schedule: np.ndarray,
    seed: int,
) -> tuple[Any, dict[str, Any], str]:
    seed_everything(seed, int(loop["runtime"]["threads"]))
    model = build_model(loop["model"])
    assert_pattern_value_model(model)
    initial_hash = _model_state_hash(model)
    training = loop["training"]
    metrics = train_from_replay(
        model,
        graph,
        samples,
        steps=int(schedule.shape[0]),
        batch_size=int(schedule.shape[1]),
        learning_rate=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        value_weight=float(training["value_weight"]),
        policy_weight=float(training["policy_weight"]),
        seed=seed,
        batch_indices=schedule,
    )
    return model, metrics, initial_hash


def build_contrasts(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, (high, low) in CONTRASTS.items():
        contrast: dict[str, Any] = {"high": high, "low": low}
        for endpoint in ("arena_score", "zero_regret_gain", "value_sign_gain"):
            values = [
                float(row["arms"][high][endpoint])
                - float(row["arms"][low][endpoint])
                for row in rows
            ]
            interval = paired_interval(values, critical)
            interval["standard_deviation"] = float(
                interval["standard_error"] * math.sqrt(interval["count"])
            )
            interval["positive_seed_count"] = sum(value > 0.0 for value in values)
            interval["zero_seed_count"] = sum(value == 0.0 for value in values)
            interval["negative_seed_count"] = sum(value < 0.0 for value in values)
            contrast[endpoint] = interval
        output[name] = contrast
    return output


def build_recommendation(
    contrasts: dict[str, Any],
    gate: dict[str, Any],
    mean_advancing_generations: float,
    minimum_advancing_generations: float,
) -> dict[str, Any]:
    if mean_advancing_generations < minimum_advancing_generations:
        return {
            "status": "INCONCLUSIVE",
            "finding": "causal_pack_did_not_advance_enough_deployed_parents",
            "generation_composition_strength_signal": None,
            "decision": "diagnose_promotion_before_strength_attribution",
            "promotable": False,
        }
    primary = contrasts["generation_composition"]["arena_score"]
    minimum = float(gate["minimum_practical_arena_gain"])
    passes = float(primary["mean"]) >= minimum and float(primary["lower"]) > 0.0
    excludes_practical = float(primary["upper"]) < minimum
    common = {
        "primary_contrast": "MIX_OUTCOME_minus_G1_WIDE_OUTCOME",
        "primary_endpoint": "paired_common_search_arena_score",
        "primary_mean": float(primary["mean"]),
        "primary_ci95": [float(primary["lower"]), float(primary["upper"])],
        "minimum_practical_arena_gain": minimum,
        "promotable": False,
    }
    if passes:
        return {
            **common,
            "status": "PASS",
            "finding": "generation_mix_makes_pattern_eval_stronger_at_equal_unique_volume",
            "generation_composition_strength_signal": True,
            "decision": "replicate_M21P_on_fresh_seeds_before_any_transfer",
        }
    if excludes_practical:
        return {
            **common,
            "status": "FAIL",
            "finding": "generation_mix_practical_strength_gain_excluded_on_pattern_eval",
            "generation_composition_strength_signal": False,
            "decision": "do_not_reconstruct_M23_mix_shape_without_new_hypothesis",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "generation_mix_strength_effect_underpowered_on_pattern_eval",
        "generation_composition_strength_signal": None,
        "decision": "replicate_with_power_sized_fresh_seed_count",
    }


def _write_outputs(result: dict[str, Any], run_dir: Path, compact_output: Path) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "result.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != SCHEMA
            or replayed.get("milestone") != "M21-P"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M21-P reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None,
    completed: int,
    total: int,
    last_seed: int,
    started: float,
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_learning_signal_progress.v1",
        "milestone": "M21-P",
        "completed_seeds": completed,
        "total_seeds": total,
        "last_completed_seed": last_seed,
        "elapsed_seconds": elapsed,
        "seeds_per_minute": rate,
        "eta_remaining_seconds": (total - completed) / rate * 60.0 if rate > 0 else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_m21p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
    progress_output: Path | None = None,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M21-P requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M21-P split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    train_starts = np.asarray(
        [state for state in train if graph.terminal_value(int(state)) is None],
        dtype=np.int64,
    )
    tensors = solved_tensors(oracle, graph)
    response_batch = int(base_loop["development"]["batch_size"])
    schedule_config = config["training_schedule"]
    steps = int(schedule_config["total_steps"])
    train_batch = int(schedule_config["batch_size"])
    schedule_offset = int(schedule_config["seed_offset"])
    strength = config["strength_arena"]
    arena_config = ArenaConfig(
        pairs=int(strength["pairs"]),
        max_plies=int(base_loop["arena"]["max_plies"]),
        search_depth=int(base_loop["arena"]["search_depth"]),
        node_budget=int(base_loop["arena"]["node_budget"]),
        epsilon=float(strength["epsilon"]),
        confidence_z=float(strength["confidence_z"]),
        confidence_unit=str(strength["confidence_unit"]),
        start_state_source="provided",
    )

    rows: list[dict[str, Any]] = []
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    for raw_seed in config["paired_seeds"]:
        seed = int(raw_seed)
        loop = deepcopy(base_loop)
        loop["seed"] = seed
        execution = execute_loop(loop, oracle, development, train, train_mask)
        per_generation = {
            generation: [
                sample
                for sample in execution.samples
                if int(sample.generation) == generation
                and bool(train_mask[int(sample.state_id)])
            ]
            for generation in range(1, 9)
        }
        fit_seed = seed + schedule_offset
        seed_everything(fit_seed, int(loop["runtime"]["threads"]))
        initial = build_model(loop["model"])
        assert_pattern_value_model(initial)
        initial_hash = _model_state_hash(initial)
        before = response_metrics(
            initial, graph, tensors, oracle, development, response_batch
        )

        wide_config = deepcopy(loop["self_play"])
        wide_config["games"] = int(config["wide_games"])
        wide_config["game_schedule"] = None
        wide_raw = generate_self_play(
            graph,
            initial,
            loop_module._parse_self_play(wide_config),
            1,
            seed + int(config["wide_seed_offset"]),
            train_starts,
        ).samples
        wide = [sample for sample in wide_raw if bool(train_mask[int(sample.state_id)])]
        pools, census = build_pools(per_generation, wide, graph, seed)
        unit = int(census["unit_rows_per_generation"])
        unit_schedule = _random_schedule(unit, steps, train_batch, fit_seed + 11)
        wide_schedule = _random_schedule(8 * unit, steps, train_batch, fit_seed + 88)
        arena_seed = int(strength["seed_base"]) + seed
        arm_rows: dict[str, Any] = {}
        arena_start_hash: str | None = None
        for arm in ARM_ORDER:
            schedule = (
                wide_schedule
                if arm in {"MIX_OUTCOME", "G1_WIDE_OUTCOME"}
                else unit_schedule
            )
            candidate, training_metrics, arm_initial_hash = _fit(
                loop, graph, pools[arm], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError("M21-P arms did not share the initial PatternEval")
            after = response_metrics(
                candidate, graph, tensors, oracle, development, response_batch
            )
            arena = run_arena(
                graph,
                candidate,
                initial,
                arena_config,
                arena_seed,
                development,
            )
            current_start_hash = digest(arena["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = current_start_hash
            elif current_start_hash != arena_start_hash:
                raise RuntimeError("M21-P arena starts diverged across arms")
            arm_rows[arm] = {
                "zero_regret_gain": float(after["zero_regret_rate"])
                - float(before["zero_regret_rate"]),
                "value_sign_gain": float(after["value_sign_accuracy"])
                - float(before["value_sign_accuracy"]),
                "after": after,
                "arena_score": float(arena["score"]),
                "arena": arena,
                "sample_pool_rows": len(pools[arm]),
                "sample_identity_hash": census["identity_hash_by_arm"][arm],
                "replay_fingerprint": replay_fingerprint(pools[arm]),
                "training": training_metrics,
                "oracle_training_signal": False,
            }
        row = {
            "seed": seed,
            "initial": before,
            "pack": {
                **census,
                "ladder_advance_count": sum(
                    bool(record["promotion"]["provisional_advance"])
                    for record in execution.core["generations"]
                ),
                "raw_ladder_replay_fingerprint": replay_fingerprint(execution.samples),
                "wide_raw_replay_fingerprint": replay_fingerprint(wide_raw),
                "shared_initial_model_hash": initial_hash,
                "shared_arena_start_hash": arena_start_hash,
                "same_schedule_for_primary_arms": True,
                "training_rows_are_train_only": all(
                    bool(train_mask[int(sample.state_id)])
                    for pool in pools.values()
                    for sample in pool
                ),
            },
            "arms": arm_rows,
        }
        rows.append(row)
        (run_dir / f"seed-{seed}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_progress(
            progress_output, len(rows), len(config["paired_seeds"]), seed, started
        )

    if not all(row["pack"]["training_rows_are_train_only"] for row in rows):
        raise RuntimeError("M21-P consumed a non-train replay row")
    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    aggregate = {
        "paired_seed_count": len(rows),
        "arms": {
            arm: {
                "mean_arena_score": mean(row["arms"][arm]["arena_score"] for row in rows),
                "mean_zero_regret_gain": mean(
                    row["arms"][arm]["zero_regret_gain"] for row in rows
                ),
                "mean_value_sign_gain": mean(
                    row["arms"][arm]["value_sign_gain"] for row in rows
                ),
                "mean_sample_pool_rows": mean(
                    row["arms"][arm]["sample_pool_rows"] for row in rows
                ),
            }
            for arm in ARM_ORDER
        },
        "contrasts": contrasts,
        "mean_ladder_advance_count": mean(
            row["pack"]["ladder_advance_count"] for row in rows
        ),
        "all_training_rows_train_only": True,
        "all_primary_schedules_paired": True,
        "all_arena_starts_paired": True,
    }
    recommendation = build_recommendation(
        contrasts,
        config["scientific_gate"],
        float(aggregate["mean_ladder_advance_count"]),
        float(config["promotion_control"]["minimum_advancing_generations"]),
    )
    protocol = {
        "schema": SCHEMA,
        "milestone": "M21-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARM_ORDER),
        "contrasts": CONTRASTS,
        "primary_endpoint": config["scientific_gate"]["primary_endpoint"],
        "strength_arena": strength,
        "source_evidence": config["source_evidence"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M21-P",
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "oracle_training_signal": False,
        },
        "promotable": False,
    }
    result["result_hash"] = digest(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    _write_outputs(result, run_dir, compact_output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    parser.add_argument("--progress-output", type=Path)
    args = parser.parse_args()
    result = run_m21p(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
        args.progress_output,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
