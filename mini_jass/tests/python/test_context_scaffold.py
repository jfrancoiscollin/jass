"""Shared-gradient and exact-export contracts for the contextual scaffold."""

from __future__ import annotations

import numpy as np
import torch

from mini_jass_lab.context_scaffold import ContextualPatternScaffold
from mini_jass_lab.patterns import PLAYABLE, PatternSet


def _features() -> torch.Tensor:
    rows = np.zeros((4, 4 * PLAYABLE + 2), dtype=np.float32)
    positions = (
        ((0, 0), (6, 1), (9, 2)),
        ((2, 1), (5, 0), (11, 3)),
        ((3, 0), (7, 1), (12, 2)),
        ((1, 3), (6, 2), (8, 1)),
    )
    for row, pieces in enumerate(positions):
        for square, plane in pieces:
            rows[row, plane * PLAYABLE + square] = 1.0
        rows[row, 4 * PLAYABLE] = float(row % 2)
        rows[row, 4 * PLAYABLE + 1] = row / 20.0
    return torch.from_numpy(rows)


def test_initialization_is_seeded_and_initializes_every_training_head() -> None:
    patterns = PatternSet.from_window(2)
    first = ContextualPatternScaffold(patterns, seed=270501)
    second = ContextualPatternScaffold(patterns, seed=270501)
    different = ContextualPatternScaffold(patterns, seed=270502)
    assert all(
        torch.equal(first.state_dict()[name], second.state_dict()[name])
        for name in first.state_dict()
    )
    assert not torch.equal(first.bucket_embedding, different.bucket_embedding)
    assert torch.equal(first.value_head, torch.eye(1, 10).squeeze(0))
    assert torch.count_nonzero(first.context_head) == first.context_head.numel()
    assert (
        torch.count_nonzero(first.delta_context_head)
        == first.delta_context_head.numel()
    )
    assert torch.count_nonzero(first.residual_head) == first.residual_head.numel()
    assert not any("policy" in name for name, _ in first.named_parameters())


def test_scalar_export_matches_the_scaffold_value_path() -> None:
    scaffold = ContextualPatternScaffold(PatternSet.from_window(2), seed=270501)
    features = _features()
    with torch.no_grad():
        scaffold.value_head.copy_(torch.linspace(-0.5, 0.5, 10))
        scaffold.shared_bias.copy_(torch.linspace(0.1, -0.1, 10))
        scaffold.value_bias.fill_(0.07)
        expected = scaffold(features)["value"]
        exported = scaffold.export_pattern_eval()
        actual, logits = exported(features)
    assert torch.max(torch.abs(expected - actual)).item() <= 1.0e-6
    assert torch.count_nonzero(logits) == 0
    assert exported.value_only is True


def test_auxiliary_gradient_changes_an_exported_scalar_bucket() -> None:
    scaffold = ContextualPatternScaffold(PatternSet.from_window(2), seed=270501)
    features = _features()
    before = scaffold.export_pattern_eval().bucket_weight.detach().clone()
    optimizer = torch.optim.SGD(scaffold.parameters(), lr=0.01)
    outputs = scaffold(features)
    target = torch.full_like(outputs["context"], 0.5)
    loss = torch.mean((outputs["context"] - target) ** 2)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    assert scaffold.bucket_embedding.grad is not None
    assert torch.count_nonzero(scaffold.bucket_embedding.grad) > 0
    optimizer.step()
    after = scaffold.export_pattern_eval().bucket_weight.detach()
    assert torch.any(before != after)
