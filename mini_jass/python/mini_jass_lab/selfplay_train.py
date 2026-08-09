"""Training updates driven exclusively by replay targets."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as functional
from torch import nn

from .game_graph import GameGraph
from .model import masked_policy_logits
from .model_factory import is_value_only
from .replay import ReplaySample


def train_from_replay(
    model: nn.Module,
    graph: GameGraph,
    samples: list[ReplaySample],
    steps: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    value_weight: float,
    policy_weight: float,
    seed: int,
    batch_indices: np.ndarray | None = None,
) -> dict[str, float | int | bool | str]:
    if not samples:
        raise ValueError("replay training requires samples")
    if steps < 1 or batch_size < 1:
        raise ValueError("training steps and batch size must be positive")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    features = torch.from_numpy(graph.features[state_ids])
    values = torch.tensor([sample.value_target for sample in samples], dtype=torch.float32)
    value_only = is_value_only(model)
    if value_only and float(policy_weight) != 0.0:
        raise ValueError("a value-only model requires policy_weight=0")
    if value_only:
        legal = None
        policies = None
    else:
        legal = torch.from_numpy(graph.legal_mask[state_ids])
        policies = torch.from_numpy(np.stack([sample.policy_target for sample in samples]))
        if torch.any(policies[~legal] != 0):
            raise ValueError("replay policy assigns probability to illegal actions")
        if not torch.allclose(
            policies.sum(dim=1), torch.ones(len(samples)), atol=1.0e-6
        ):
            raise ValueError("every replay policy must sum to one")

    optimizer = torch.optim.AdamW(
        model.parameters(), learning_rate, weight_decay=weight_decay
    )
    generator = torch.Generator().manual_seed(seed)
    explicit_batches: np.ndarray | None = None
    if batch_indices is not None:
        explicit_batches = np.asarray(batch_indices, dtype=np.int64)
        if explicit_batches.shape != (steps, batch_size):
            raise ValueError(
                "explicit replay batch schedule must have shape "
                f"({steps}, {batch_size})"
            )
        if np.any(explicit_batches < 0) or np.any(explicit_batches >= len(samples)):
            raise ValueError("explicit replay batch schedule contains an invalid index")
    totals = {"loss": 0.0, "value_loss": 0.0, "policy_loss": 0.0}
    model.train()
    for step in range(steps):
        batch = (
            torch.from_numpy(explicit_batches[step])
            if explicit_batches is not None
            else torch.randint(0, len(samples), (batch_size,), generator=generator)
        )
        predicted, logits = model(features[batch])
        value_loss = functional.mse_loss(predicted, values[batch])
        if value_only:
            policy_loss = predicted.sum() * 0.0
        else:
            assert legal is not None and policies is not None
            masked = masked_policy_logits(logits, legal[batch])
            policy_loss = -(
                policies[batch] * functional.log_softmax(masked, dim=1)
            ).sum(dim=1).mean()
        loss = value_weight * value_loss + policy_weight * policy_loss
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        totals["loss"] += float(loss.detach())
        totals["value_loss"] += float(value_loss.detach())
        totals["policy_loss"] += float(policy_loss.detach())
    metrics: dict[str, float | int | bool | str | None] = {
        "steps": steps,
        "batch_size": batch_size,
        "sample_pool": len(samples),
        "value_only": value_only,
        "policy_trained": not value_only,
        "action_source": "search" if value_only else "policy_head",
        "explicit_batch_schedule": explicit_batches is not None,
        **{key: value / steps for key, value in totals.items()},
    }
    # ⚠️ `None`, PAS `0.0` : une perte de politique a zero se lit comme une
    # politique parfaitement apprise. Une evaluation n'en a aucune.
    if value_only:
        metrics["policy_loss"] = None
    return metrics
