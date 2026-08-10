"""Leakage-free deterministic targets for contextual outcome supervision."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np

from .context import COMPONENTS, context_matrix, state_from_oracle


def baseline_values(
    contexts: np.ndarray,
    weights: Mapping[str, float],
    tau: float,
) -> np.ndarray:
    matrix = np.asarray(contexts, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != len(COMPONENTS):
        raise ValueError("context matrix has the wrong shape")
    coefficients = np.asarray([float(weights[name]) for name in COMPONENTS])
    scale = float(tau)
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("context baseline tau must be positive and finite")
    return np.tanh(matrix @ coefficients / scale)


def transition_context_delta(
    oracle: object,
    parent_state_id: int,
    child_state_id: int,
) -> np.ndarray:
    parent = int(parent_state_id)
    child = int(child_state_id)
    children = np.asarray(getattr(oracle, "action_children"))[parent]
    if child not in children[children >= 0]:
        raise ValueError("context delta requires a legal recorded transition")
    mover = state_from_oracle(oracle, parent).side_to_move
    parent_context = context_matrix(oracle, (parent,), (mover,))[0]
    child_context = context_matrix(oracle, (child,), (mover,))[0]
    return child_context - parent_context


def build_context_targets(
    oracle: object,
    state_ids: Iterable[int],
    child_ids: Iterable[int],
    terminal_wdl: Iterable[float],
    *,
    baseline_weights: Mapping[str, float],
    tau: float,
    residual_clip: float,
) -> dict[str, np.ndarray]:
    states = np.asarray(tuple(int(value) for value in state_ids), dtype=np.int64)
    children = np.asarray(tuple(int(value) for value in child_ids), dtype=np.int64)
    outcomes = np.asarray(
        tuple(float(value) for value in terminal_wdl), dtype=np.float64
    )
    if (
        states.ndim != 1
        or children.shape != states.shape
        or outcomes.shape != states.shape
    ):
        raise ValueError(
            "context target records must have aligned one-dimensional fields"
        )
    if np.any(~np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("terminal WDL targets must be exactly -1, 0 or 1")
    terminal = np.asarray(getattr(oracle, "terminal_status"))[states]
    if np.any(terminal != 0):
        raise ValueError("residual targets require non-terminal pre-move states")

    contexts = context_matrix(oracle, states)
    deltas = np.asarray(
        [
            transition_context_delta(oracle, int(parent), int(child))
            for parent, child in zip(states, children)
        ],
        dtype=np.float64,
    )
    baseline = baseline_values(contexts, baseline_weights, tau)
    clip = float(residual_clip)
    if not np.isfinite(clip) or clip <= 0.0:
        raise ValueError("residual clip must be positive and finite")
    residual = np.clip(outcomes - baseline, -clip, clip)
    return {
        "context": contexts,
        "delta_context": deltas,
        "baseline": baseline,
        "residual": residual,
        "terminal_wdl": outcomes,
    }
