"""Paired replay training for the contextual PatternEval scaffold."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import torch.nn.functional as functional

from .context_scaffold import ContextualPatternScaffold
from .context_targets import build_context_targets
from .game_graph import GameGraph
from .replay import ReplaySample

DEPLOYABLE_ARMS = (
    "WDL_ONLY",
    "WDL_PLUS_CONTEXT",
    "WDL_PLUS_DELTA_CONTEXT",
    "WDL_PLUS_RESIDUAL",
    "WDL_PLUS_FULL_CONTEXT",
)


def tensor_state_hash(module: torch.nn.Module) -> str:
    """Hash a module state without depending on PyTorch serialization."""
    hasher = hashlib.sha256()
    for name, tensor in sorted(module.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        hasher.update(name.encode("utf-8"))
        hasher.update(str(value.dtype).encode("ascii"))
        hasher.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        hasher.update(value.numpy().tobytes(order="C"))
    return hasher.hexdigest()


def batch_schedule(
    pool_size: int,
    steps: int,
    batch_size: int,
    seed: int,
) -> np.ndarray:
    if pool_size < 1 or steps < 1 or batch_size < 1:
        raise ValueError("contextual batch schedule dimensions must be positive")
    return np.random.default_rng(int(seed)).integers(
        0,
        int(pool_size),
        size=(int(steps), int(batch_size)),
        dtype=np.int64,
    )


def batch_schedule_hash(indices: np.ndarray) -> str:
    schedule = np.asarray(indices, dtype=np.int64)
    if schedule.ndim != 2 or not schedule.size:
        raise ValueError("contextual batch schedule must be a non-empty matrix")
    hasher = hashlib.sha256()
    hasher.update(np.asarray(schedule.shape, dtype=np.int64).tobytes())
    hasher.update(schedule.tobytes(order="C"))
    return hasher.hexdigest()


def contextual_replay_targets(
    oracle: object,
    graph: GameGraph,
    samples: Sequence[ReplaySample],
    *,
    allowed_state_mask: np.ndarray,
    baseline_weights: Mapping[str, float],
    tau: float,
    residual_clip: float,
) -> dict[str, np.ndarray]:
    """Build all targets from one immutable train-only behavior replay."""
    if not samples:
        raise ValueError("contextual replay requires samples")
    mask = np.asarray(allowed_state_mask, dtype=np.bool_)
    if mask.shape != (graph.state_count,):
        raise ValueError("contextual replay cohort mask has the wrong shape")
    state_ids = np.asarray([int(sample.state_id) for sample in samples], dtype=np.int64)
    if np.any(state_ids < 0) or np.any(state_ids >= graph.state_count):
        raise ValueError("contextual replay contains an invalid state")
    if not np.all(mask[state_ids]):
        raise ValueError("contextual deployable replay crossed the train boundary")

    child_ids: list[int] = []
    for sample in samples:
        if sample.selected_action is None:
            raise ValueError(
                "contextual replay is missing its selected behavior action"
            )
        action = int(sample.selected_action)
        state = int(sample.state_id)
        if (
            action < 0
            or action >= graph.action_count
            or not graph.legal_mask[state, action]
        ):
            raise ValueError("contextual replay contains an illegal selected action")
        child_ids.append(graph.child(state, action))

    targets = build_context_targets(
        oracle,
        state_ids,
        child_ids,
        (sample.value_target for sample in samples),
        baseline_weights=baseline_weights,
        tau=float(tau),
        residual_clip=float(residual_clip),
    )
    targets["state_ids"] = state_ids
    targets["child_ids"] = np.asarray(child_ids, dtype=np.int64)
    targets["selected_actions"] = np.asarray(
        [int(sample.selected_action) for sample in samples], dtype=np.int64
    )
    return targets


def _arm_weights(config: Mapping[str, Any], arm: str) -> tuple[float, float, float]:
    if arm not in DEPLOYABLE_ARMS:
        raise ValueError(f"unsupported contextual deployable arm: {arm}")
    arm_config = config["c1_arms"][arm]
    if arm_config.get("value_target") != "terminal_wdl":
        raise ValueError("deployable contextual arms must keep terminal WDL")
    if arm_config.get("oracle_training_signal") is not False:
        raise ValueError("deployable contextual arm crossed the oracle boundary")
    return (
        float(arm_config["beta_context"]),
        float(arm_config["gamma_delta_context"]),
        float(arm_config["eta_residual"]),
    )


def train_contextual_from_replay(
    scaffold: ContextualPatternScaffold,
    graph: GameGraph,
    targets: Mapping[str, np.ndarray],
    *,
    arm: str,
    config: Mapping[str, Any],
    indices: np.ndarray,
    learning_rate: float,
    weight_decay: float,
) -> dict[str, float | int | bool | str | None]:
    """Train one arm on an explicit schedule shared by every paired arm."""
    schedule = np.asarray(indices, dtype=np.int64)
    if schedule.ndim != 2 or not schedule.size:
        raise ValueError("contextual training requires an explicit batch schedule")
    state_ids = np.asarray(targets["state_ids"], dtype=np.int64)
    if np.any(schedule < 0) or np.any(schedule >= state_ids.size):
        raise ValueError("contextual batch schedule contains an invalid replay index")
    beta, gamma, eta = _arm_weights(config, arm)

    features = torch.from_numpy(graph.features[state_ids]).to(
        dtype=scaffold.bucket_embedding.dtype,
        device=scaffold.bucket_embedding.device,
    )
    value_target = torch.as_tensor(
        targets["terminal_wdl"], dtype=features.dtype, device=features.device
    )
    context_target = torch.as_tensor(
        targets["context"], dtype=features.dtype, device=features.device
    )
    delta_target = torch.as_tensor(
        targets["delta_context"], dtype=features.dtype, device=features.device
    )
    residual_target = torch.as_tensor(
        targets["residual"], dtype=features.dtype, device=features.device
    )
    optimizer = torch.optim.AdamW(
        scaffold.parameters(),
        lr=float(learning_rate),
        weight_decay=float(weight_decay),
    )
    initial_export = scaffold.export_pattern_eval()
    initial_export_hash = tensor_state_hash(initial_export)
    initial_bucket = initial_export.bucket_weight.detach().cpu().clone()
    totals = {
        "loss": 0.0,
        "value_loss": 0.0,
        "context_loss": 0.0,
        "delta_context_loss": 0.0,
        "residual_loss": 0.0,
    }
    scaffold.train()
    for row in schedule:
        batch = torch.from_numpy(row).to(device=features.device)
        output = scaffold(features[batch])
        value_loss = functional.mse_loss(output["value"], value_target[batch])
        context_loss = functional.mse_loss(output["context"], context_target[batch])
        delta_loss = functional.mse_loss(output["delta_context"], delta_target[batch])
        residual_loss = functional.mse_loss(output["residual"], residual_target[batch])
        loss = (
            value_loss + beta * context_loss + gamma * delta_loss + eta * residual_loss
        )
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        totals["loss"] += float(loss.detach())
        totals["value_loss"] += float(value_loss.detach())
        totals["context_loss"] += float(context_loss.detach())
        totals["delta_context_loss"] += float(delta_loss.detach())
        totals["residual_loss"] += float(residual_loss.detach())

    final_export = scaffold.export_pattern_eval()
    bucket_delta = torch.abs(final_export.bucket_weight.detach().cpu() - initial_bucket)
    steps, batch_size = schedule.shape
    return {
        "arm": arm,
        "steps": int(steps),
        "batch_size": int(batch_size),
        "sample_pool": int(state_ids.size),
        "explicit_batch_schedule": True,
        "batch_schedule_hash": batch_schedule_hash(schedule),
        "value_only": True,
        "policy_trained": False,
        "policy_loss": None,
        "action_source": "search",
        "initial_export_hash": initial_export_hash,
        "final_export_hash": tensor_state_hash(final_export),
        "changed_exported_bucket_count": int(torch.count_nonzero(bucket_delta).item()),
        "maximum_exported_bucket_change": float(torch.max(bucket_delta).item()),
        **{name: total / int(steps) for name, total in totals.items()},
    }
