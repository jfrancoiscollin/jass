from __future__ import annotations

import pytest

from mini_jass_lab.model import MiniJassMLP
from mini_jass_lab.model_factory import build_model, is_value_only, model_descriptor
from mini_jass_lab.pattern_eval import PatternEval


def test_legacy_configs_still_default_to_the_frozen_mlp() -> None:
    model = build_model(
        {
            "hidden_size": 32,
            "linear": False,
            "action_count": 72,
            "enforce_baseline_limit": True,
        }
    )
    assert isinstance(model, MiniJassMLP)
    assert is_value_only(model) is False


def test_the_production_like_config_builds_a_folded_value_only_model() -> None:
    model = build_model(
        {
            "architecture": "folded_pattern_value",
            "pattern_window": 3,
            "include_reversible_plies": True,
        }
    )
    assert isinstance(model, PatternEval)
    assert is_value_only(model) is True
    descriptor = model_descriptor(model)
    assert descriptor["architecture"] == "folded_pattern_value"
    assert descriptor["side_aware_exact_fold"] is True
    assert descriptor["value_only"] is True


def test_unknown_model_options_fail_closed() -> None:
    with pytest.raises(ValueError, match="unexpected folded-pattern"):
        build_model({"architecture": "folded_pattern_value", "hidden_size": 32})
