"""Construction explicite des architectures Mini-Jass.

Les anciennes experiences restent sur leur MLP gele. Le baseline
``folded_pattern_value`` est l'analogue production : tables de patterns
lineaires pliees, valeur seule, politique fournie par la recherche.
"""

from __future__ import annotations

from typing import Any

from torch import nn

from .model import MiniJassMLP, ModelConfig, parameter_count
from .pattern_eval import PatternEval
from .patterns import PatternSet

MLP_ARCHITECTURE = "mlp"
PATTERN_VALUE_ARCHITECTURE = "folded_pattern_value"


def build_model(config: dict[str, Any]) -> nn.Module:
    resolved = dict(config)
    architecture = resolved.pop("architecture", MLP_ARCHITECTURE)
    if architecture == MLP_ARCHITECTURE:
        return MiniJassMLP(ModelConfig(**resolved))
    if architecture == PATTERN_VALUE_ARCHITECTURE:
        allowed = {"pattern_window", "include_reversible_plies"}
        unexpected = set(resolved) - allowed
        if unexpected:
            raise ValueError(
                "unexpected folded-pattern model options: "
                + ", ".join(sorted(unexpected))
            )
        window = int(resolved.get("pattern_window", 3))
        return PatternEval(
            PatternSet.from_window(window),
            include_reversible_plies=bool(
                resolved.get("include_reversible_plies", True)
            ),
        )
    raise ValueError(f"unknown Mini-Jass model architecture: {architecture}")


def is_value_only(model: nn.Module) -> bool:
    return bool(getattr(model, "value_only", False))


def model_descriptor(model: nn.Module) -> dict[str, Any]:
    if isinstance(model, PatternEval):
        return {
            "architecture": PATTERN_VALUE_ARCHITECTURE,
            "pattern_set": model.pattern_set.describe(),
            "side_aware_exact_fold": True,
            "include_reversible_plies": model.include_reversible_plies,
            "value_only": True,
            "parameter_count": parameter_count(model),
        }
    if isinstance(model, MiniJassMLP):
        return {
            "architecture": MLP_ARCHITECTURE,
            "hidden_size": model.config.hidden_size,
            "linear": model.config.linear,
            "value_only": False,
            "parameter_count": parameter_count(model),
        }
    raise TypeError(f"unsupported Mini-Jass model type: {type(model).__name__}")
