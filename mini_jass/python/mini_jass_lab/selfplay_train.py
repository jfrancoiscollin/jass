"""Training updates driven exclusively by replay targets."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as functional

from .game_graph import GameGraph
from .model import MiniJassMLP, masked_policy_logits
from .replay import ReplaySample


def train_from_replay(
    model: MiniJassMLP,
    graph: GameGraph,
    samples: list[ReplaySample],
    steps: int,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    value_weight: float,
    policy_weight: float,
    seed: int,
) -> dict[str, float | int]:
    if not samples:
        raise ValueError("replay training requires samples")
    if steps < 1 or batch_size < 1:
        raise ValueError("training steps and batch size must be positive")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    features = torch.from_numpy(graph.features[state_ids])
    legal = torch.from_numpy(graph.legal_mask[state_ids])
    values = torch.tensor([sample.value_target for sample in samples], dtype=torch.float32)
    policies = torch.from_numpy(np.stack([sample.policy_target for sample in samples]))
    if torch.any(policies[~legal] != 0):
        raise ValueError("replay policy assigns probability to illegal actions")
    if not torch.allclose(policies.sum(dim=1), torch.ones(len(samples)), atol=1.0e-6):
        raise ValueError("every replay policy must sum to one")

    optimizer = torch.optim.AdamW(
        model.parameters(), learning_rate, weight_decay=weight_decay
    )
    generator = torch.Generator().manual_seed(seed)
    totals = {"loss": 0.0, "value_loss": 0.0, "policy_loss": 0.0}
    model.train()
    for _ in range(steps):
        batch = torch.randint(0, len(samples), (batch_size,), generator=generator)
        predicted, logits = model(features[batch])
        value_loss = functional.mse_loss(predicted, values[batch])
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
    return {
        "steps": steps,
        "batch_size": batch_size,
        "sample_pool": len(samples),
        **{key: value / steps for key, value in totals.items()},
    }
