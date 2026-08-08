"""Execution and per-arm aggregation for M18."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import numpy as np

import mini_jass_lab.loop as loop_module
from mini_jass_lab.arena import ArenaConfig, run_arena
from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.model import MiniJassMLP, ModelConfig, model_hash
from mini_jass_lab.oracle import OracleArrays
from mini_jass_lab.selfplay import generate_self_play
from mini_jass_lab.train import seed_everything

from m18_wdl_config import _mean
from m18_wdl_mechanics import (
    _deployed_states_by_rung,
    _frozen_generator,
    _model_metrics,
    _probe_config,
    _stamp_execution_contract,
    _start_signature,
    _wdl_quality,
)


def _run_arm_seed(
    *,
    arm: str,
    spec: dict[str, Any],
    seed: int,
    base_loop: dict[str, Any],
    oracle: OracleArrays,
    graph: GameGraph,
    development_indices: np.ndarray,
    training_start_indices: np.ndarray,
    tensors: dict[str, Any],
    config: dict[str, Any],
    run_dir: Path,
    probe_depth_override: int | None = None,
) -> dict[str, Any]:
    loop_config = deepcopy(base_loop)
    loop_config["seed"] = int(seed)
    loop_config["promotion"]["minimum_development_improvement"] = float(
        config["promotion_contract"]["forced_development_floor"]
    )
    if spec["promotion_rule"] == "always":
        loop_config["promotion"]["minimum_arena_lower_bound"] = float(
            config["promotion_contract"]["always_advance_arena_floor"]
        )
    if isinstance(spec["search_depth"], int):
        loop_config["self_play"]["search_depth"] = int(spec["search_depth"])

    original_generate = loop_module.generate_self_play
    try:
        if spec["generator_source"] == "initial_model":
            loop_module.generate_self_play = _frozen_generator(original_generate)
        elif spec["generator_source"] != "evolving_parent":
            raise ValueError(f"unknown M18 generator source: {spec['generator_source']}")
        execution = loop_module.execute_loop(
            loop_config,
            oracle,
            development_indices,
            training_start_indices,
        )
    finally:
        loop_module.generate_self_play = original_generate

    _stamp_execution_contract(execution, arm, spec)
    seed_everything(int(seed), int(loop_config["runtime"]["threads"]))
    initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
    rungs = [int(rung) for rung in config["report_rungs"]]
    deployed_states = _deployed_states_by_rung(
        deepcopy(initial.state_dict()),
        execution.candidate_states,
        execution.core["generations"],
        rungs,
    )

    nonterminal_train = np.asarray(
        [
            int(state_id)
            for state_id in training_start_indices
            if graph.terminal_value(int(state_id)) is None
        ],
        dtype=np.int64,
    )
    probe = config["fixed_probe"]
    probe_config = _probe_config(
        loop_config, int(probe["games"]), probe_depth_override
    )
    probe_seed = int(probe["seed_base"]) + int(seed)
    batch = int(loop_config["development"]["batch_size"])
    before = _model_metrics(initial, tensors, oracle, development_indices, batch)

    by_rung: dict[str, Any] = {}
    probe_signature: str | None = None
    for rung in rungs:
        model = MiniJassMLP(ModelConfig(**loop_config["model"]))
        model.load_state_dict(deployed_states[str(rung)])
        observed = _model_metrics(model, tensors, oracle, development_indices, batch)
        generated = generate_self_play(
            graph, model, probe_config, 1, probe_seed, nonterminal_train
        )
        starts = [sample for sample in generated.samples if int(sample.ply) == 0]
        signature = _start_signature(generated.samples)
        if probe_signature is None:
            probe_signature = signature
        elif signature != probe_signature:
            raise ValueError("M18 fixed probe changed its start schedule across rungs")
        by_rung[str(rung)] = {
            "development": {
                "value_sign_delta": observed["value_sign_accuracy"]
                - before["value_sign_accuracy"],
                "optimal_mass_delta": observed["optimal_probability_mass"]
                - before["optimal_probability_mass"],
                "absolute": observed,
            },
            "probe_start_wdl": _wdl_quality(starts, oracle),
            "probe_all_wdl": _wdl_quality(generated.samples, oracle),
            "probe_start_signature": signature,
            "deployed_model_hash": model_hash(model),
        }

    training_by_generation: dict[str, Any] = {}
    training_start_signatures: dict[str, str] = {}
    for generation in range(1, int(config["ladder_max"]) + 1):
        samples = [
            sample for sample in execution.samples if int(sample.generation) == generation
        ]
        starts = [sample for sample in samples if int(sample.ply) == 0]
        training_by_generation[str(generation)] = {
            "start_wdl": _wdl_quality(starts, oracle),
            "all_wdl": _wdl_quality(samples, oracle),
            "coverage": execution.core["generations"][generation - 1]["coverage"],
        }
        training_start_signatures[str(generation)] = _start_signature(samples)

    final_model = MiniJassMLP(ModelConfig(**loop_config["model"]))
    final_model.load_state_dict(execution.final_state)
    final_arena_config = ArenaConfig(
        pairs=int(probe["arena_pairs"]),
        max_plies=int(loop_config["arena"]["max_plies"]),
        search_depth=int(loop_config["arena"]["search_depth"]),
        node_budget=int(loop_config["arena"]["node_budget"]),
        epsilon=0.0,
        confidence_z=1.96,
    )
    final_arena = run_arena(
        graph,
        final_model,
        initial,
        final_arena_config,
        int(probe["arena_seed_base"]) + int(seed),
    )
    advancing = [
        bool(record["promotion"]["provisional_advance"])
        for record in execution.core["generations"]
    ]
    row = {
        "seed": int(seed),
        "arm": arm,
        "by_rung": by_rung,
        "training_label_quality_by_generation": training_by_generation,
        "training_start_signatures": training_start_signatures,
        "probe_start_signature": probe_signature,
        "advancing_generations": int(sum(advancing)),
        "advance_flags": advancing,
        "final_arena_vs_initial": final_arena,
        "execution_hash": execution.core["execution_hash"],
        "final_model_hash": execution.core["final_model_hash"],
        "initial_model_hash": execution.core["initial_model_hash"],
        "oracle_causal_reads": 0,
    }
    if probe_depth_override is not None:
        # Ecrit SOUS GARDE : `result_hash` de M18 couvre `seed_results`, donc un
        # champ ajoute inconditionnellement casserait la reproductibilite du
        # verdict `cpx62-1206`. Meme raison que la garde de `value_target_source`.
        row["probe_search_depth"] = int(probe_depth_override)
        # Le compute du bras, mesure et non postule : la reserve « la profondeur
        # baisse mais le budget de noeuds reste » se teste ici, elle ne se
        # commente plus. Precedent : `maximum_consumed_node_imbalance` de M8.
        row["loop_consumed_nodes"] = sum(
            int(record["self_play"]["search"]["consumed_nodes"])
            for record in execution.core["generations"]
        )
    seed_dir = run_dir / arm
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / f"seed-{seed}.json").write_text(
        json.dumps(
            {"summary": row, "execution_core": execution.core},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return row


def _aggregate_arm(rows: list[dict[str, Any]], rungs: list[int]) -> dict[str, Any]:
    final = str(rungs[-1])
    result = {
        "successful_run_count": len(rows),
        "mean_advancing_generations": _mean(
            [float(row["advancing_generations"]) for row in rows]
        ),
        "seeds_with_zero_advance": sum(
            1 for row in rows if int(row["advancing_generations"]) == 0
        ),
        "mean_probe_start_exact_rate_by_rung": {
            str(rung): _mean(
                [float(row["by_rung"][str(rung)]["probe_start_wdl"]["exact_rate"]) for row in rows]
            )
            for rung in rungs
        },
        "mean_probe_start_true_decisive_labelled_draw_rate_by_rung": {
            str(rung): _mean(
                [float(row["by_rung"][str(rung)]["probe_start_wdl"]["true_decisive_labelled_draw_rate"]) for row in rows]
            )
            for rung in rungs
        },
        "mean_development_value_sign_delta_by_rung": {
            str(rung): _mean(
                [float(row["by_rung"][str(rung)]["development"]["value_sign_delta"]) for row in rows]
            )
            for rung in rungs
        },
        "mean_development_optimal_mass_delta_by_rung": {
            str(rung): _mean(
                [float(row["by_rung"][str(rung)]["development"]["optimal_mass_delta"]) for row in rows]
            )
            for rung in rungs
        },
        "mean_final_development_value_sign_delta": _mean(
            [float(row["by_rung"][final]["development"]["value_sign_delta"]) for row in rows]
        ),
        "mean_final_development_optimal_mass_delta": _mean(
            [float(row["by_rung"][final]["development"]["optimal_mass_delta"]) for row in rows]
        ),
        "mean_final_arena_score_vs_initial": _mean(
            [float(row["final_arena_vs_initial"]["score"]) for row in rows]
        ),
        "probe_start_signatures": sorted({row["probe_start_signature"] for row in rows}),
        "training_start_signatures": {
            str(generation): sorted(
                {row["training_start_signatures"][str(generation)] for row in rows}
            )
            for generation in range(1, int(rungs[-1]) + 1)
        },
    }
    return result
