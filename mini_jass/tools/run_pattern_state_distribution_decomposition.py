#!/usr/bin/env python3
"""M18-P: decompose PatternEval generation gains into states, labels and path."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
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

SCHEMA = "mini_jass.pattern_state_distribution_decomposition.v1"
ARM_ORDER = (
    "G1_ONLY_OUTCOME",
    "G8_ONLY_OUTCOME",
    "G1_WIDE_OUTCOME",
    "MIX_OUTCOME",
    "G1_WIDE_EXACT",
    "MIX_EXACT",
    "MIX_SEQUENTIAL_OUTCOME",
)
CONTRASTS = {
    "state_distribution_exact": ("MIX_EXACT", "G1_WIDE_EXACT"),
    "deployable_composition": ("MIX_OUTCOME", "G1_WIDE_OUTCOME"),
    "label_noise_under_mix": ("MIX_EXACT", "MIX_OUTCOME"),
    "label_noise_under_g1_wide": ("G1_WIDE_EXACT", "G1_WIDE_OUTCOME"),
    "optimizer_path": ("MIX_SEQUENTIAL_OUTCOME", "MIX_OUTCOME"),
    "unique_sample_volume": ("G1_WIDE_OUTCOME", "G1_ONLY_OUTCOME"),
    "recency": ("G8_ONLY_OUTCOME", "G1_ONLY_OUTCOME"),
}


def _arena_score_lower_bound(
    score: float, pairs: int, confidence_z: float, confidence_unit: str
) -> float:
    observations = 2 * pairs if confidence_unit == "games" else pairs
    standard_error = math.sqrt(max(score * (1.0 - score), 0.0) / observations)
    return max(0.0, score - confidence_z * standard_error)


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M18-P":
        raise ValueError("unexpected M18-P schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M18-P arms changed after preregistration")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 20 or len(set(seeds)) != 20:
        raise ValueError("M18-P requires 20 unique paired seeds")
    earlier = set(range(262001, 264021))
    if set(seeds) & earlier:
        raise ValueError("M18-P must not reuse an M17-P/P2/P2R seed")
    source = config.get("source_replication", {})
    if (
        source.get("schema")
        != "mini_jass.pattern_generation_ladder_replication.v1"
        or source.get("milestone") != "M17-P2R"
        or source.get("result_hash")
        != "c868949d2f1027889e6e76fd081e763aedcac7840f6105e1f18175e5c66685ea"
    ):
        raise ValueError("M18-P source replication is not the frozen M17-P2R result")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("generation_reads_oracle_labels") is not False
        or boundaries.get("sample_selection_reads_oracle_labels") is not False
        or boundaries.get("exact_oracle_training_arms")
        != ["G1_WIDE_EXACT", "MIX_EXACT"]
        or boundaries.get("cohorts_read") != ["train", "development"]
        or boundaries.get("cohorts_sealed") != ["frozen_test"]
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M18-P crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1" or int(loop["generations"]) != 1:
        raise ValueError("M18-P requires the one-generation Pattern base recipe")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M18-P requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M18-P cannot train a policy head")
    schedule = config["training_schedule"]
    steps = int(schedule["total_steps"])
    cycles = int(schedule["sequential_cycles"])
    if cycles != 8 or steps < cycles or steps % cycles:
        raise ValueError("M18-P sequential schedule must divide eight cycles exactly")
    if int(schedule["batch_size"]) != int(loop["training"]["batch_size"]):
        raise ValueError("M18-P batch size differs from the frozen training recipe")
    if int(config["wide_games"]) != 8 * int(loop["self_play"]["games"]):
        raise ValueError("M18-P G1_WIDE must use exactly eight times the G1 games")

    control = config["promotion_control"]
    pairs = int(control["arena_pairs"])
    loop["arena"].update(
        {
            "pairs": pairs,
            "epsilon": float(control["arena_epsilon"]),
            "start_state_source": "provided",
            "confidence_unit": str(control["arena_confidence_unit"]),
        }
    )
    if control["arena_start_state_source"] != "development":
        raise ValueError("M18-P requires varied development arena starts")
    lower = _arena_score_lower_bound(
        float(control["neutral_arena_score"]),
        pairs,
        float(loop["arena"]["confidence_z"]),
        str(control["arena_confidence_unit"]),
    )
    if not math.isclose(
        lower, float(control["neutral_score_lower_bound"]), abs_tol=1e-12
    ):
        raise ValueError("M18-P neutral arena bound changed")
    if lower < float(loop["promotion"]["minimum_arena_lower_bound"]):
        raise ValueError("M18-P inherited an underpowered arena")
    loop["generations"] = 8
    return deepcopy(config), loop


def _take(
    samples: list[ReplaySample], count: int, rng: np.random.Generator
) -> list[ReplaySample]:
    if count > len(samples):
        raise ValueError(f"sample pool needs {count} rows, only {len(samples)} exist")
    indices = np.sort(rng.choice(len(samples), size=count, replace=False))
    return [samples[int(index)] for index in indices]


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
    seed: int,
) -> tuple[dict[str, list[ReplaySample]], list[list[ReplaySample]], dict[str, Any]]:
    if set(per_generation) != set(range(1, 9)):
        raise ValueError("M18-P requires all eight generation pools")
    unit = min(len(per_generation[generation]) for generation in range(1, 9))
    if unit < 2:
        raise ValueError("M18-P needs at least two train rows in every generation")
    selected = [
        _take(
            per_generation[generation],
            unit,
            np.random.default_rng(seed * 1_000_003 + generation),
        )
        for generation in range(1, 9)
    ]
    mix = [sample for generation in selected for sample in generation]
    wide_selected = _take(
        wide, len(mix), np.random.default_rng(seed * 1_000_003 + 404)
    )
    pools = {
        "G1_ONLY_OUTCOME": selected[0],
        "G8_ONLY_OUTCOME": selected[7],
        "G1_WIDE_OUTCOME": wide_selected,
        "MIX_OUTCOME": mix,
    }
    if len(pools["G1_WIDE_OUTCOME"]) != len(pools["MIX_OUTCOME"]):
        raise RuntimeError("M18-P primary state pools have unequal row counts")
    census = {
        "unit_rows_per_generation": unit,
        "rows_by_generation_before_equalization": {
            str(generation): len(per_generation[generation])
            for generation in range(1, 9)
        },
        "rows_by_pool": {name: len(pool) for name, pool in pools.items()},
        "unique_states_by_pool": {
            name: len({int(sample.state_id) for sample in pool})
            for name, pool in pools.items()
        },
        "mix_identity_hash": _identity_hash("ladder", mix),
        "g1_wide_identity_hash": _identity_hash("g1_wide", wide_selected),
        "mix_replay_fingerprint": replay_fingerprint(mix),
        "g1_wide_replay_fingerprint": replay_fingerprint(wide_selected),
    }
    return pools, selected, census


def _exact(samples: list[ReplaySample], values: np.ndarray) -> list[ReplaySample]:
    return [
        replace(sample, value_target=float(values[int(sample.state_id)]))
        for sample in samples
    ]


def build_mix_schedules(
    unit: int, steps: int, batch_size: int, seed: int
) -> tuple[np.ndarray, list[np.ndarray], dict[str, Any]]:
    if steps % 8:
        raise ValueError("M18-P mix schedule requires steps divisible by eight")
    per_cycle = steps // 8
    local: list[np.ndarray] = []
    global_grouped: list[np.ndarray] = []
    for generation in range(8):
        schedule = np.random.default_rng(seed + generation).integers(
            0, unit, size=(per_cycle, batch_size), dtype=np.int64
        )
        local.append(schedule)
        global_grouped.append(schedule + generation * unit)
    grouped = np.concatenate(global_grouped, axis=0)
    order = np.random.default_rng(seed + 99).permutation(steps)
    one_shot = grouped[order]
    same_draw_multiset = bool(
        np.array_equal(np.sort(grouped.reshape(-1)), np.sort(one_shot.reshape(-1)))
    )
    if not same_draw_multiset:
        raise RuntimeError("M18-P optimizer arms do not share the same sample draws")
    audit = {
        "steps": steps,
        "batch_size": batch_size,
        "draw_count": int(steps * batch_size),
        "same_draw_multiset": same_draw_multiset,
        "grouped_schedule_hash": digest(grouped.tolist()),
        "one_shot_schedule_hash": digest(one_shot.tolist()),
    }
    return one_shot, local, audit


def _random_schedule(
    pool_size: int, steps: int, batch_size: int, seed: int
) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        0, pool_size, size=(steps, batch_size), dtype=np.int64
    )


def _fit(
    loop: dict[str, Any],
    graph: GameGraph,
    samples: list[ReplaySample],
    schedule: np.ndarray,
    seed: int,
) -> tuple[Any, dict[str, Any]]:
    seed_everything(seed, int(loop["runtime"]["threads"]))
    model = build_model(loop["model"])
    assert_pattern_value_model(model)
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
    return model, metrics


def _fit_sequential(
    loop: dict[str, Any],
    graph: GameGraph,
    generations: list[list[ReplaySample]],
    schedules: list[np.ndarray],
    seed: int,
) -> tuple[Any, list[dict[str, Any]]]:
    seed_everything(seed, int(loop["runtime"]["threads"]))
    model = build_model(loop["model"])
    assert_pattern_value_model(model)
    training = loop["training"]
    metrics: list[dict[str, Any]] = []
    for generation, (samples, schedule) in enumerate(
        zip(generations, schedules, strict=True), start=1
    ):
        row = train_from_replay(
            model,
            graph,
            samples,
            steps=int(schedule.shape[0]),
            batch_size=int(schedule.shape[1]),
            learning_rate=float(training["learning_rate"]),
            weight_decay=float(training["weight_decay"]),
            value_weight=float(training["value_weight"]),
            policy_weight=float(training["policy_weight"]),
            seed=seed + generation,
            batch_indices=schedule,
        )
        row["generation"] = generation
        metrics.append(row)
    return model, metrics


def build_contrasts(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, (high, low) in CONTRASTS.items():
        contrast: dict[str, Any] = {"high": high, "low": low}
        for endpoint in ("zero_regret_gain", "value_sign_gain"):
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
        out[name] = contrast
    return out


def _passes(interval: dict[str, Any], gate: dict[str, Any]) -> bool:
    confidence = (
        not bool(gate["require_ci_above_zero"])
        or float(interval["lower"]) > 0.0
    )
    return confidence and float(interval["mean"]) >= float(
        gate["minimum_practical_gain"]
    )


def build_recommendation(
    contrasts: dict[str, Any],
    gate: dict[str, Any],
    mean_advancing_generations: float = 8.0,
    minimum_advancing_generations: float = 1.0,
) -> dict[str, Any]:
    if mean_advancing_generations < minimum_advancing_generations:
        return {
            "status": "INCONCLUSIVE",
            "finding": "causal_pack_did_not_advance_enough_deployed_parents",
            "identified_mechanism": None,
            "decision": "diagnose_promotion_process_before_mechanism_attribution",
            "promotable": False,
        }
    distribution_exact = _passes(
        contrasts["state_distribution_exact"]["zero_regret_gain"], gate
    )
    distribution_honest = _passes(
        contrasts["deployable_composition"]["zero_regret_gain"], gate
    )
    label_noise = _passes(
        contrasts["label_noise_under_mix"]["zero_regret_gain"], gate
    )
    optimizer_path = _passes(
        contrasts["optimizer_path"]["zero_regret_gain"], gate
    )
    if distribution_exact and distribution_honest:
        finding = "late_generation_state_distribution_explains_compounding"
        decision = "replicate_state_distribution_factor_on_fresh_seeds"
        mechanism = "state_distribution"
    elif optimizer_path:
        finding = "sequential_optimizer_path_explains_compounding"
        decision = "replicate_optimizer_path_factor_on_fresh_seeds"
        mechanism = "optimizer_path"
    elif distribution_exact:
        finding = "late_state_distribution_signal_is_not_recovered_from_outcomes"
        decision = "isolate_label_distribution_interaction"
        mechanism = None
    elif distribution_honest:
        finding = "native_target_shift_or_interaction_not_state_distribution"
        decision = "isolate_generation_conditioned_label_shift"
        mechanism = None
    else:
        finding = "state_distribution_and_optimizer_path_do_not_explain_compounding"
        decision = "refine_factorization_before_advancing"
        mechanism = None
    return {
        "status": "PASS",
        "finding": finding,
        "identified_mechanism": mechanism,
        "state_distribution_exact_pass": distribution_exact,
        "deployable_composition_pass": distribution_honest,
        "label_noise_pass": label_noise,
        "optimizer_path_pass": optimizer_path,
        "minimum_practical_gain": float(gate["minimum_practical_gain"]),
        "decision": decision,
        "promotable": False,
    }


def _write_outputs(
    result: dict[str, Any], run_dir: Path, compact_output: Path
) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "result.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != SCHEMA
            or replayed.get("milestone") != "M18-P"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M18-P write/read reporting round-trip failed: {path}")


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
    remaining = total - completed
    payload = {
        "schema": "mini_jass.pattern_state_distribution_progress.v1",
        "milestone": "M18-P",
        "completed_seeds": completed,
        "total_seeds": total,
        "last_completed_seed": last_seed,
        "elapsed_seconds": elapsed,
        "seeds_per_minute": rate,
        "eta_remaining_seconds": remaining / rate * 60.0 if rate > 0.0 else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_m18p(
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
        raise ValueError(f"M18-P requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M18-P split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    starts = np.asarray(
        [state for state in train if graph.terminal_value(int(state)) is None],
        dtype=np.int64,
    )
    tensors = solved_tensors(oracle, graph)
    batch = int(base_loop["development"]["batch_size"])
    schedule_config = config["training_schedule"]
    steps = int(schedule_config["total_steps"])
    train_batch = int(schedule_config["batch_size"])
    schedule_offset = int(schedule_config["seed_offset"])

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
        seed_everything(seed, int(loop["runtime"]["threads"]))
        initial = build_model(loop["model"])
        assert_pattern_value_model(initial)
        before = response_metrics(initial, graph, tensors, oracle, development, batch)

        wide_config = deepcopy(loop["self_play"])
        wide_config["games"] = int(config["wide_games"])
        wide_config["game_schedule"] = None
        wide_raw = generate_self_play(
            graph,
            initial,
            loop_module._parse_self_play(wide_config),
            1,
            seed + int(config["wide_seed_offset"]),
            starts,
        ).samples
        wide = [sample for sample in wide_raw if bool(train_mask[int(sample.state_id)])]
        pools, selected_generations, census = build_pools(per_generation, wide, seed)
        pools["G1_WIDE_EXACT"] = _exact(pools["G1_WIDE_OUTCOME"], oracle.values)
        pools["MIX_EXACT"] = _exact(pools["MIX_OUTCOME"], oracle.values)
        pools["MIX_SEQUENTIAL_OUTCOME"] = pools["MIX_OUTCOME"]

        unit = int(census["unit_rows_per_generation"])
        mix_schedule, sequential_schedules, schedule_audit = build_mix_schedules(
            unit, steps, train_batch, seed + schedule_offset
        )
        g1_schedule = _random_schedule(
            unit, steps, train_batch, seed + schedule_offset + 501
        )
        g8_schedule = _random_schedule(
            unit, steps, train_batch, seed + schedule_offset + 508
        )
        schedules = {
            "G1_ONLY_OUTCOME": g1_schedule,
            "G8_ONLY_OUTCOME": g8_schedule,
            "G1_WIDE_OUTCOME": mix_schedule,
            "MIX_OUTCOME": mix_schedule,
            "G1_WIDE_EXACT": mix_schedule,
            "MIX_EXACT": mix_schedule,
        }
        arm_rows: dict[str, Any] = {}
        for arm in ARM_ORDER:
            if arm == "MIX_SEQUENTIAL_OUTCOME":
                model, training_metrics = _fit_sequential(
                    loop,
                    graph,
                    selected_generations,
                    sequential_schedules,
                    seed + schedule_offset,
                )
            else:
                model, training_metrics = _fit(
                    loop,
                    graph,
                    pools[arm],
                    schedules[arm],
                    seed + schedule_offset,
                )
            after = response_metrics(model, graph, tensors, oracle, development, batch)
            arm_rows[arm] = {
                "zero_regret_gain": float(after["zero_regret_rate"])
                - float(before["zero_regret_rate"]),
                "value_sign_gain": float(after["value_sign_accuracy"])
                - float(before["value_sign_accuracy"]),
                "after": after,
                "sample_pool_rows": len(pools[arm]),
                "sample_identity_hash": _identity_hash(
                    "ladder" if "WIDE" not in arm else "g1_wide", pools[arm]
                ),
                "replay_fingerprint": replay_fingerprint(pools[arm]),
                "training": training_metrics,
                "oracle_value_targets_consumed": arm.endswith("_EXACT"),
            }
        changed_mix = sum(
            left.value_target != right.value_target
            for left, right in zip(
                pools["MIX_OUTCOME"], pools["MIX_EXACT"], strict=True
            )
        )
        changed_wide = sum(
            left.value_target != right.value_target
            for left, right in zip(
                pools["G1_WIDE_OUTCOME"], pools["G1_WIDE_EXACT"], strict=True
            )
        )
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
                "schedule": schedule_audit,
                "mix_exact_changed_target_count": changed_mix,
                "g1_wide_exact_changed_target_count": changed_wide,
                "training_rows_are_train_cohort_only": all(
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
            progress_output,
            len(rows),
            len(config["paired_seeds"]),
            seed,
            started,
        )

    if not all(
        row["pack"]["training_rows_are_train_cohort_only"]
        and row["pack"]["schedule"]["same_draw_multiset"]
        for row in rows
    ):
        raise RuntimeError("M18-P causal pack failed a train/path contract")
    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    aggregate = {
        "paired_seed_count": len(rows),
        "arms": {
            arm: {
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
        "all_path_draw_multisets_equal": True,
    }
    recommendation = build_recommendation(
        contrasts,
        config["scientific_gate"],
        float(aggregate["mean_ladder_advance_count"]),
        float(config["promotion_control"]["minimum_advancing_generations"]),
    )
    protocol = {
        "schema": SCHEMA,
        "milestone": "M18-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARM_ORDER),
        "contrasts": CONTRASTS,
        "primary_endpoint": config["scientific_gate"]["primary_endpoint"],
        "single_generated_pack_per_seed": True,
        "sample_draw_multiset_equal_for_path_contrast": True,
        "source_replication": config["source_replication"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result = {
        "schema": SCHEMA,
        "milestone": "M18-P",
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "exact_oracle_labels_consumed_only_by": [
                "G1_WIDE_EXACT",
                "MIX_EXACT",
            ],
        },
    }
    result["result_hash"] = digest(result)
    _write_outputs(result, run_dir, compact_output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--progress-output", type=Path)
    parser.add_argument("--execution-host")
    args = parser.parse_args()
    result = run_m18p(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
        args.progress_output,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "finding": result["recommendation"]["finding"],
                "result_hash": result["result_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
