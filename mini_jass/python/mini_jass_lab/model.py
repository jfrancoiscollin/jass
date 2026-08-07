"""Normative Mini-Jass value/policy MLP and capacity controls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

import torch
from torch import nn

INPUT_COUNT = 54
ACTION_COUNT = 72
BASELINE_HIDDEN = 32
BASELINE_PARAMETER_LIMIT = 5500
BASELINE_PARAMETER_COUNT = 5225


@dataclass(frozen=True)
class ModelConfig:
    hidden_size: int = BASELINE_HIDDEN
    linear: bool = False
    input_count: int = INPUT_COUNT
    action_count: int = ACTION_COUNT
    enforce_baseline_limit: bool = True
    parameter_limit: int | None = None


class MiniJassMLP(nn.Module):
    def __init__(self, config: ModelConfig = ModelConfig()) -> None:
        super().__init__()
        if config.input_count < 1 or config.action_count < 1:
            raise ValueError("input and action counts must be positive")
        if config.input_count == INPUT_COUNT and config.action_count != ACTION_COUNT:
            raise ValueError("Mini-Jass L1 action vocabulary must contain 72 actions")
        self.config = config
        if config.linear:
            self.backbone = nn.Identity()
            output_size = config.input_count
        else:
            if config.hidden_size <= 0:
                raise ValueError("hidden_size must be positive")
            self.backbone = nn.Sequential(
                nn.Linear(config.input_count, config.hidden_size),
                nn.ReLU(),
                nn.Linear(config.hidden_size, config.hidden_size),
                nn.ReLU(),
            )
            output_size = config.hidden_size
        self.value_head = nn.Linear(output_size, 1)
        self.policy_head = nn.Linear(output_size, config.action_count)

        count = parameter_count(self)
        is_l1_baseline = (
            not config.linear
            and config.hidden_size == BASELINE_HIDDEN
            and config.input_count == INPUT_COUNT
            and config.action_count == ACTION_COUNT
        )
        if is_l1_baseline:
            if count != BASELINE_PARAMETER_COUNT:
                raise RuntimeError(f"baseline parameter count changed: {count}")
        limit = config.parameter_limit
        if limit is None and is_l1_baseline:
            limit = BASELINE_PARAMETER_LIMIT
        if config.enforce_baseline_limit and limit is not None and count > int(limit):
            raise ValueError(f"model exceeds the {limit}-parameter ceiling")

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.backbone(features)
        value = torch.tanh(self.value_head(hidden)).squeeze(-1)
        policy_logits = self.policy_head(hidden)
        return value, policy_logits


def parameter_count(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def masked_policy_logits(logits: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
    return logits.masked_fill(~legal_mask, torch.finfo(logits.dtype).min)


def model_hash(model: nn.Module) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        hasher.update(name.encode())
        hasher.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return hasher.hexdigest()
