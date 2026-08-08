"""M18 target-quality microscope and causal loop mechanics."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import numpy as np
import torch

import mini_jass_lab.loop as loop_module
from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.model import MiniJassMLP
from mini_jass_lab.oracle import OracleArrays
from mini_jass_lab.selfplay import GenerationResult, SelfPlayConfig
from mini_jass_lab.train import evaluate, uniform_optimal_targets

from m18_wdl_config import WDL_NAME, _digest


def _wdl_quality(samples: list[Any], oracle: OracleArrays) -> dict[str, Any]:
    confusion = {
        truth: {label: 0 for label in ("W", "D", "L")}
        for truth in ("W", "D", "L")
    }
    if not samples:
        return {
            "count": 0,
            "unique_states": 0,
            "exact_rate": None,
            "mae": None,
            "true_decisive_labelled_draw_rate": None,
            "confusion": confusion,
        }
    state_ids = np.asarray([int(sample.state_id) for sample in samples], dtype=np.int64)
    labels = np.asarray(
        [float(sample.value_target) for sample in samples], dtype=np.float32
    )
    truth = oracle.values[state_ids].astype(np.float32)
    if not np.all(np.isin(labels, (-1.0, 0.0, 1.0))):
        raise ValueError("M18 WDL microscope received a non-ternary training label")
    for true_value, label_value in zip(truth, labels, strict=True):
        confusion[WDL_NAME[int(true_value)]][WDL_NAME[int(label_value)]] += 1
    decisive = truth != 0.0
    false_draw_rate = (
        float(np.mean(labels[decisive] == 0.0)) if bool(np.any(decisive)) else 0.0
    )
    return {
        "count": len(samples),
        "unique_states": int(np.unique(state_ids).size),
        "exact_rate": float(np.mean(labels == truth)),
        "mae": float(np.mean(np.abs(labels - truth))),
        "true_decisive_labelled_draw_rate": false_draw_rate,
        "confusion": confusion,
    }


def _frozen_generator(
    original_generate: Callable[..., GenerationResult],
) -> Callable[..., GenerationResult]:
    """Freeze only the model producing WDL; learner and arena gate may evolve."""
    frozen_model: Any | None = None

    def wrapped(
        graph: Any,
        model: Any,
        config: Any,
        generation: int,
        seed: int,
        start_state_ids: Any = None,
    ) -> GenerationResult:
        nonlocal frozen_model
        if frozen_model is None:
            frozen_model = deepcopy(model)
        return original_generate(
            graph, frozen_model, config, generation, seed, start_state_ids
        )

    return wrapped


def _verify_promotion_contract(execution: Any, rule: str) -> None:
    for record in execution.core["generations"]:
        promotion = record["promotion"]
        if promotion["development_pass"] is not True:
            raise ValueError("M18 development gate was not neutralised")
        if rule == "arena_only":
            if bool(promotion["provisional_advance"]) != bool(promotion["arena_pass"]):
                raise ValueError("M18 arena-only promotion diverged from arena_pass")
        elif rule == "always":
            if not bool(promotion["arena_pass"]) or not bool(
                promotion["provisional_advance"]
            ):
                raise ValueError("M18 forced-advance arm failed to advance")
        else:
            raise ValueError(f"unknown M18 promotion rule: {rule}")


def _stamp_execution_contract(execution: Any, arm: str, spec: dict[str, Any]) -> None:
    _verify_promotion_contract(execution, str(spec["promotion_rule"]))
    core = execution.core
    core["oracle_contract"]["usage"] = (
        "posthoc_observer_only_not_training_generation_or_promotion"
    )
    core["m18_policy_iteration_contract"] = {
        "arm": arm,
        "generator_source": spec["generator_source"],
        "search_depth": spec["search_depth"],
        "promotion_rule": spec["promotion_rule"],
        "value_target": "terminal_selfplay_wdl",
        "oracle_causal_reads": 0,
        "promotable": False,
    }
    core["execution_hash"] = _digest(
        {key: value for key, value in core.items() if key != "execution_hash"}
    )


def _deployed_states_by_rung(
    initial_state: dict[str, Any],
    candidate_states: list[dict[str, Any]],
    generation_records: list[dict[str, Any]],
    rungs: list[int],
) -> dict[str, dict[str, Any]]:
    requested = set(int(rung) for rung in rungs)
    if 0 not in requested:
        raise ValueError("M18 deployed-state ladder must include rung zero")
    result = {"0": deepcopy(initial_state)}
    deployed = deepcopy(initial_state)
    for generation, (candidate_state, record) in enumerate(
        zip(candidate_states, generation_records, strict=True), start=1
    ):
        if bool(record["promotion"]["provisional_advance"]):
            deployed = deepcopy(candidate_state)
        if generation in requested:
            result[str(generation)] = deepcopy(deployed)
    if set(result) != {str(rung) for rung in rungs}:
        raise ValueError("M18 could not reconstruct every deployed rung")
    return result


def _development_tensors(
    oracle: OracleArrays, graph: GameGraph
) -> dict[str, torch.Tensor]:
    return {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def _model_metrics(
    model: MiniJassMLP,
    tensors: dict[str, torch.Tensor],
    oracle: OracleArrays,
    indices: np.ndarray,
    batch_size: int,
) -> dict[str, float]:
    raw = evaluate(model, tensors, oracle, indices, batch_size)
    return {
        "value_sign_accuracy": float(raw["value_sign_accuracy"]),
        "optimal_probability_mass": float(raw["optimal_probability_mass"]),
    }


def _probe_config(loop_config: dict[str, Any], games: int) -> SelfPlayConfig:
    payload = deepcopy(loop_config["self_play"])
    payload["games"] = int(games)
    payload["game_schedule"] = None
    return loop_module._parse_self_play(payload)


def _start_signature(samples: list[Any]) -> str:
    rows = [
        (int(sample.game_id), int(sample.state_id))
        for sample in samples
        if int(sample.ply) == 0
    ]
    return _digest(rows)
