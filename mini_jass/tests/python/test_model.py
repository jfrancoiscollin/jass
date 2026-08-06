from __future__ import annotations

import pytest
import torch

from mini_jass_lab.model import (
    BASELINE_PARAMETER_COUNT,
    MiniJassMLP,
    ModelConfig,
    masked_policy_logits,
    parameter_count,
)


def test_baseline_and_capacity_control_parameter_counts() -> None:
    assert parameter_count(MiniJassMLP()) == BASELINE_PARAMETER_COUNT == 5225
    assert parameter_count(MiniJassMLP(ModelConfig(hidden_size=8))) == 1169
    assert parameter_count(MiniJassMLP(ModelConfig(linear=True))) == 4015
    assert parameter_count(MiniJassMLP(ModelConfig(hidden_size=64))) == 12425


def test_forward_shapes_and_legal_mask() -> None:
    model = MiniJassMLP()
    values, logits = model(torch.zeros((3, 54)))
    assert values.shape == (3,)
    assert logits.shape == (3, 72)
    legal = torch.zeros((3, 72), dtype=torch.bool)
    legal[:, 7] = True
    assert masked_policy_logits(logits, legal).argmax(dim=1).tolist() == [7, 7, 7]


def test_action_vocabulary_size_is_immutable() -> None:
    with pytest.raises(ValueError, match="72"):
        MiniJassMLP(ModelConfig(action_count=71))
