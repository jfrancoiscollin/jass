"""Shared contracts for the architecture-correct Mini-Jass reconstruction.

The historical experiment harnesses score the argmax of an auxiliary policy
head.  ``PatternEval`` has no such head: its answer is the move selected from
child values.  The helpers below make that response contract explicit and
keep the new ``-P`` evidence separate from the historical MLP evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

import numpy as np
import torch
from torch import nn

from .game_graph import GameGraph
from .model_factory import (
    PATTERN_VALUE_ARCHITECTURE,
    is_value_only,
    model_descriptor,
)
from .oracle import OracleArrays, uniform_optimal_targets
from .replay import ReplaySample
from .train import evaluate

RESPONSE_METRICS = (
    "zero_regret_rate",
    "optimal_top1_accuracy",
    "mean_selected_regret",
    "value_sign_accuracy",
    "value_mae",
)


def digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def solved_tensors(oracle: OracleArrays, graph: GameGraph) -> dict[str, torch.Tensor]:
    """Solved labels used only by explicitly declared evaluation/training cells."""
    return {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def assert_pattern_value_model(model: nn.Module) -> None:
    descriptor = model_descriptor(model)
    if (
        not is_value_only(model)
        or descriptor.get("architecture") != PATTERN_VALUE_ARCHITECTURE
    ):
        raise ValueError("pattern reconstruction requires folded_pattern_value")


def response_metrics(
    model: nn.Module,
    graph: GameGraph,
    tensors: dict[str, torch.Tensor],
    oracle: OracleArrays,
    indices: np.ndarray,
    batch_size: int,
) -> dict[str, Any]:
    """Score the move selected from values, never a policy-head surrogate."""
    assert_pattern_value_model(model)
    raw = evaluate(model, tensors, oracle, indices, batch_size, graph)
    if raw["action_source"] != "search_one_ply":
        raise RuntimeError("PatternEval response was not supplied by value search")
    if raw["optimal_probability_mass"] is not None:
        raise RuntimeError(
            "a value-only response cannot expose policy probability mass"
        )
    return {
        "count": int(raw["count"]),
        "playable_count": int(raw["response_count"]),
        "action_source": raw["action_source"],
        **{key: raw[key] for key in RESPONSE_METRICS},
    }


def replay_fingerprint(samples: Iterable[ReplaySample]) -> str:
    """Hash every generated field, including the full policy-target payload."""
    hasher = hashlib.sha256()
    for sample in samples:
        header = (
            f"{sample.state_id}|{sample.value_target:.17g}|{sample.generation}|"
            f"{sample.game_id}|{sample.ply}|"
        ).encode("ascii")
        policy = np.asarray(sample.policy_target, dtype=np.float32)
        hasher.update(header)
        if sample.selected_action is not None:
            hasher.update(
                f"selected_action={int(sample.selected_action)}|".encode("ascii")
            )
        hasher.update(policy.shape[0].to_bytes(4, "little", signed=False))
        hasher.update(policy.tobytes(order="C"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def mean(values: Iterable[float]) -> float:
    return float(np.mean(np.asarray(list(values), dtype=np.float64)))


def paired_interval(values: Iterable[float], z: float = 1.96) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size < 2:
        raise ValueError("paired interval requires at least two seeds")
    center = float(array.mean())
    standard_error = float(array.std(ddof=1) / math.sqrt(array.size))
    return {
        "count": int(array.size),
        "mean": center,
        "standard_error": standard_error,
        "confidence_z": float(z),
        "lower": center - float(z) * standard_error,
        "upper": center + float(z) * standard_error,
    }
