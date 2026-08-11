"""Training-only additive decomposition for production-shaped PatternEval.

Two compatible linear PatternEval scores can be trained separately and added
before the final tanh.  Their parameters then collapse exactly into one normal
PatternEval, so the experiment changes optimisation, not inference capacity.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional

from .game_graph import GameGraph
from .pattern_eval import PatternEval
from .replay import ReplaySample


# Collapsing two linear paths changes the order of float32 additions: the two
# independently reduced scores become one reduction over elementwise-summed
# weights. The expressions are algebraically identical but can differ by a
# handful of ULPs. PatternEval window-3 evaluates nine buckets plus its extra
# and bias, so 16 float32 epsilons are a conservative absolute roundoff guard.
FLOAT32_COLLAPSE_ATOL = 16.0 * float(torch.finfo(torch.float32).eps)


def zero_pattern_eval_like(model: PatternEval) -> PatternEval:
    """Clone a compatible evaluator and reset only its trainable parameters."""

    if not isinstance(model, PatternEval):
        raise TypeError("residual decomposition requires PatternEval")
    residual = deepcopy(model)
    with torch.no_grad():
        for parameter in residual.parameters():
            parameter.zero_()
    return residual


def combined_values(
    base: PatternEval, residual: PatternEval, features: torch.Tensor
) -> torch.Tensor:
    """Evaluate the two additive score paths before a collapse."""

    _assert_compatible(base, residual)
    return torch.tanh(base.raw_score(features) + residual.raw_score(features))


def collapse_pattern_evals(
    base: PatternEval, residual: PatternEval
) -> PatternEval:
    """Add compatible linear parameters into one standard PatternEval."""

    _assert_compatible(base, residual)
    collapsed = deepcopy(base)
    with torch.no_grad():
        collapsed.bucket_weight.add_(residual.bucket_weight)
        collapsed.extra_weight.add_(residual.extra_weight)
        collapsed.bias.add_(residual.bias)
    return collapsed


def train_residual_path(
    base: PatternEval,
    residual: PatternEval,
    graph: GameGraph,
    samples: list[ReplaySample],
    batch_indices: np.ndarray,
    learning_rate: float,
    weight_decay: float,
) -> dict[str, Any]:
    """Freeze ``base`` and fit only ``residual`` against the final value target."""

    _assert_compatible(base, residual)
    if not samples:
        raise ValueError("residual replay training requires samples")
    schedule = np.asarray(batch_indices, dtype=np.int64)
    if schedule.ndim != 2 or schedule.shape[0] < 1 or schedule.shape[1] < 1:
        raise ValueError("residual batch schedule must be a non-empty matrix")
    if np.any(schedule < 0) or np.any(schedule >= len(samples)):
        raise ValueError("residual batch schedule contains an invalid index")

    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    features = torch.from_numpy(graph.features[state_ids])
    targets = torch.tensor(
        [sample.value_target for sample in samples], dtype=torch.float32
    )
    base.eval()
    residual.train()
    optimizer = torch.optim.AdamW(
        residual.parameters(), learning_rate, weight_decay=weight_decay
    )
    total_loss = 0.0
    for indices in schedule:
        batch = torch.from_numpy(indices)
        with torch.no_grad():
            base_score = base.raw_score(features[batch])
        predicted = torch.tanh(base_score + residual.raw_score(features[batch]))
        loss = functional.mse_loss(predicted, targets[batch])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        total_loss += float(loss.detach())
    return {
        "steps": int(schedule.shape[0]),
        "batch_size": int(schedule.shape[1]),
        "sample_pool": len(samples),
        "loss": total_loss / float(schedule.shape[0]),
        "value_loss": total_loss / float(schedule.shape[0]),
        "policy_loss": None,
        "value_only": True,
        "policy_trained": False,
        "action_source": "search",
        "explicit_batch_schedule": True,
        "base_frozen": True,
        "combination": "tanh(base_raw_score+residual_raw_score)",
    }


def _assert_compatible(base: PatternEval, residual: PatternEval) -> None:
    if not isinstance(base, PatternEval) or not isinstance(residual, PatternEval):
        raise TypeError("additive decomposition requires PatternEval operands")
    if (
        base.class_count != residual.class_count
        or base.extras != residual.extras
        or base.bucket_count != residual.bucket_count
        or not torch.equal(base.bucket_class, residual.bucket_class)
        or not torch.equal(base.pattern_squares, residual.pattern_squares)
        or not torch.equal(base.pattern_mask, residual.pattern_mask)
        or not torch.equal(base.pattern_offset, residual.pattern_offset)
    ):
        raise ValueError("PatternEval operands are not structurally compatible")
