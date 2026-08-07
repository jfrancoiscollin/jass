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
    action_count: int = ACTION_COUNT
    enforce_baseline_limit: bool = True


class MiniJassMLP(nn.Module):
    def __init__(self, config: ModelConfig = ModelConfig()) -> None:
        super().__init__()
        if config.action_count != ACTION_COUNT:
            raise ValueError("Mini-Jass action vocabulary v1 must contain 72 actions")
        self.config = config
        if config.linear:
            self.backbone = nn.Identity()
            output_size = INPUT_COUNT
        else:
            if config.hidden_size <= 0:
                raise ValueError("hidden_size must be positive")
            self.backbone = nn.Sequential(
                nn.Linear(INPUT_COUNT, config.hidden_size),
                nn.ReLU(),
                nn.Linear(config.hidden_size, config.hidden_size),
                nn.ReLU(),
            )
            output_size = config.hidden_size
        self.value_head = nn.Linear(output_size, 1)
        self.policy_head = nn.Linear(output_size, ACTION_COUNT)

        count = parameter_count(self)
        if not config.linear and config.hidden_size == BASELINE_HIDDEN:
            if count != BASELINE_PARAMETER_COUNT:
                raise RuntimeError(f"baseline parameter count changed: {count}")
            if config.enforce_baseline_limit and count > BASELINE_PARAMETER_LIMIT:
                raise ValueError("baseline exceeds the 5,500-parameter ceiling")

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
