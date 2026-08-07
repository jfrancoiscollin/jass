from __future__ import annotations

from pathlib import Path

import torch

from mini_jass_lab.l2_transfer_gate import (
    build_l2_transfer_recommendation,
    resolve_l2_transfer_config,
)
from mini_jass_lab.model import MiniJassMLP, ModelConfig, parameter_count


def test_l2_model_dimensions_and_capacity_are_independent_from_l1() -> None:
    model = MiniJassMLP(
        ModelConfig(
            input_count=74,
            action_count=122,
            parameter_limit=8000,
        )
    )
    values, logits = model(torch.zeros((3, 74)))
    assert values.shape == (3,)
    assert logits.shape == (3, 122)
    assert parameter_count(model) == 7515


def test_m9_config_freezes_the_m8_selected_mechanism() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = resolve_l2_transfer_config(root / "configs/l2_frozen_transfer_gate.yaml")
    assert resolved["paired_seeds"] == [92001, 92002, 92003, 92004, 92005]
    assert resolved["frozen_mechanism"] == {
        "source_milestone": "M8",
        "policy_target": "score_softmax",
        "dose_arm": "strong_1024",
        "optimizer_steps": 1024,
    }
    assert resolved["loop"]["model"]["input_count"] == 74
    assert resolved["loop"]["model"]["action_count"] == 122


def test_m9_recommendation_never_directly_authorizes_10x10() -> None:
    thresholds = {
        "minimum_mean_value_sign_delta": 0.0,
        "minimum_mean_optimal_mass_delta": 0.0,
        "minimum_target_value_exact_rate": 0.70,
        "minimum_target_optimal_mass": 0.85,
    }
    passing = {
        "successful_runs": 5,
        "deterministic_replay": True,
        "mean_development_value_sign_delta": 0.02,
        "mean_development_optimal_mass_delta": 0.01,
        "selection_score_confidence_95": [0.01, 0.04],
        "mean_target_value_exact_rate": 0.75,
        "mean_target_optimal_mass": 0.90,
        "eligible_candidate_count": 1,
    }
    passed = build_l2_transfer_recommendation(passing, thresholds)
    assert passed["decision"] == "l2_replication_confirmed"
    assert passed["direct_10x10_transfer_authorized"] is False

    failing = dict(passing, mean_target_value_exact_rate=0.60)
    failed = build_l2_transfer_recommendation(failing, thresholds)
    assert failed["decision"] == "keep_l2_gate_closed"
    assert failed["implementation_preparation_authorized"] is False
