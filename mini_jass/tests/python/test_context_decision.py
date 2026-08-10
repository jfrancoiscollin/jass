"""Frozen C1+C2 sequential decision tests."""

from __future__ import annotations

import math

from mini_jass_lab.context_decision import (
    contextual_mechanism_decision,
    sequential_flat_prior_paired_score,
)


def _decision(c1: list[float], c2: list[float]) -> dict[str, object]:
    return sequential_flat_prior_paired_score(
        c1,
        c2,
        thresholds=(0.0, 0.03, 0.05, 0.10, 0.14),
        heterogeneity_maximum_z=1.96,
        signal_probability=0.95,
    )


def test_sequential_positive_signal_and_threshold_probabilities() -> None:
    report = _decision([0.08, 0.10, 0.12, 0.10], [0.09, 0.11, 0.13, 0.11])
    assert report["decision"] == "SIGNAL_ESTABLISHED"
    assert report["posterior"]["probability_score_delta_strictly_above"]["0.00"] > 0.95
    assert report["posterior"]["probability_score_delta_strictly_above"]["0.14"] < 0.05
    assert report["heterogeneity"]["heterogeneous"] is False


def test_sequential_nonpositive_and_pool_contradiction_rejections() -> None:
    nonpositive = _decision([-0.03, -0.02, -0.01], [-0.04, -0.03, -0.02])
    assert nonpositive["decision"] == "REJECTED_COMBINED_EFFECT_NONPOSITIVE"
    contradiction = _decision([0.09, 0.10, 0.11], [-0.11, -0.10, -0.09])
    assert contradiction["decision"] == "REJECTED_POOL_CONTRADICTION"
    assert contradiction["heterogeneity"]["z"] > 1.96


def test_flat_result_remains_inconclusive_and_update_is_inverse_variance() -> None:
    report = _decision([-0.01, 0.00, 0.01], [0.00, 0.01, 0.02])
    assert report["decision"] == "INCONCLUSIVE"
    pools = report["pools"]
    precision1 = 1.0 / pools["C1"]["standard_error"] ** 2
    precision2 = 1.0 / pools["C2"]["standard_error"] ** 2
    expected = (
        pools["C1"]["mean"] * precision1 + pools["C2"]["mean"] * precision2
    ) / (precision1 + precision2)
    assert math.isclose(report["posterior"]["mean"], expected)


def test_mechanism_uses_negative_mae_delta_as_improvement() -> None:
    report = contextual_mechanism_decision(
        [-0.04, -0.03, -0.02],
        [-0.05, -0.04, -0.03],
        heterogeneity_maximum_z=1.96,
        signal_probability=0.95,
    )
    assert report["posterior_mean_value_mae_delta"] < 0.0
    assert report["posterior_probability_delta_lt_zero"] > 0.95
    assert report["signal"] is True
