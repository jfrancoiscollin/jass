"""Frozen sequential decisions for the contextual C1/C2 evidence pools."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


def _pool_summary(values: Iterable[float], pool: str) -> dict[str, float | int | str]:
    array = np.asarray(list(values), dtype=np.float64)
    if array.size < 2 or not np.all(np.isfinite(array)):
        raise ValueError(f"{pool} requires at least two finite paired deltas")
    return {
        "pool": str(pool),
        "count": int(array.size),
        "mean": float(array.mean()),
        "sample_standard_deviation": float(array.std(ddof=1)),
        "standard_error": float(array.std(ddof=1) / math.sqrt(array.size)),
    }


def _strict_probability_above(
    mean: float, standard_error: float, threshold: float
) -> float:
    if standard_error == 0.0:
        return float(mean > threshold)
    z = (float(threshold) - mean) / standard_error
    return float(0.5 * math.erfc(z / math.sqrt(2.0)))


def sequential_flat_prior_paired_score(
    c1_deltas: Iterable[float],
    c2_deltas: Iterable[float],
    *,
    thresholds: Sequence[float],
    heterogeneity_maximum_z: float,
    signal_probability: float,
) -> dict[str, object]:
    """Apply the frozen inverse-variance normal C1-then-C2 update.

    Each evidence pool contributes its paired-score mean and plug-in paired
    standard error.  An improper flat prior updated with C1 yields the C1
    normal posterior; multiplying that posterior by the independent C2 normal
    likelihood is the usual inverse-variance update.
    """
    c1 = _pool_summary(c1_deltas, "C1")
    c2 = _pool_summary(c2_deltas, "C2")
    se1 = float(c1["standard_error"])
    se2 = float(c2["standard_error"])
    mean1 = float(c1["mean"])
    mean2 = float(c2["mean"])
    if se1 == 0.0 and se2 == 0.0:
        posterior_mean = mean1 if mean1 == mean2 else (mean1 + mean2) / 2.0
        posterior_se = 0.0
    elif se1 == 0.0:
        posterior_mean, posterior_se = mean1, 0.0
    elif se2 == 0.0:
        posterior_mean, posterior_se = mean2, 0.0
    else:
        precision1 = 1.0 / (se1 * se1)
        precision2 = 1.0 / (se2 * se2)
        posterior_se = math.sqrt(1.0 / (precision1 + precision2))
        posterior_mean = (mean1 * precision1 + mean2 * precision2) / (
            precision1 + precision2
        )

    joint_se = math.sqrt(se1 * se1 + se2 * se2)
    if joint_se == 0.0:
        heterogeneity_z = 0.0 if mean1 == mean2 else float(np.finfo(np.float64).max)
    else:
        heterogeneity_z = abs(mean1 - mean2) / joint_se
    heterogeneous = heterogeneity_z > float(heterogeneity_maximum_z)
    probabilities = {
        format(float(threshold), ".2f"): _strict_probability_above(
            posterior_mean, posterior_se, float(threshold)
        )
        if math.isfinite(posterior_mean)
        else 0.0
        for threshold in thresholds
    }
    p_positive = _strict_probability_above(posterior_mean, posterior_se, 0.0)
    if heterogeneous:
        decision = "REJECTED_POOL_CONTRADICTION"
    elif posterior_mean <= 0.0:
        decision = "REJECTED_COMBINED_EFFECT_NONPOSITIVE"
    elif p_positive > float(signal_probability):
        decision = "SIGNAL_ESTABLISHED"
    else:
        decision = "INCONCLUSIVE"
    return {
        "estimator": "sequential_flat_prior_paired_score_v1",
        "likelihood": "normal_pool_mean_with_plugin_paired_standard_error_v1",
        "initial_prior": "improper_flat_on_score_delta",
        "update_order": ["C1", "C2"],
        "C1_posterior_becomes_C2_prior": True,
        "pools": {"C1": c1, "C2": c2},
        "posterior": {
            "mean": posterior_mean,
            "standard_error": posterior_se,
            "interval_95": {
                "lower": posterior_mean - 1.96 * posterior_se,
                "upper": posterior_mean + 1.96 * posterior_se,
            },
            "probability_score_delta_strictly_above": probabilities,
        },
        "heterogeneity": {
            "statistic": "absolute_pool_difference_over_joint_standard_error",
            "z": heterogeneity_z,
            "maximum_z": float(heterogeneity_maximum_z),
            "heterogeneous": heterogeneous,
        },
        "signal_probability_strictly_greater_than": float(signal_probability),
        "decision": decision,
        "automatic_promotion": False,
    }


def contextual_mechanism_decision(
    c1_value_mae_deltas: Iterable[float],
    c2_value_mae_deltas: Iterable[float],
    *,
    heterogeneity_maximum_z: float,
    signal_probability: float,
) -> dict[str, object]:
    """Apply the same frozen update with negative MAE delta as improvement."""
    c1 = list(c1_value_mae_deltas)
    c2 = list(c2_value_mae_deltas)
    improvement = sequential_flat_prior_paired_score(
        (-value for value in c1),
        (-value for value in c2),
        thresholds=(0.0,),
        heterogeneity_maximum_z=heterogeneity_maximum_z,
        signal_probability=signal_probability,
    )
    posterior = improvement["posterior"]
    assert isinstance(posterior, dict)
    probability = posterior["probability_score_delta_strictly_above"]
    assert isinstance(probability, dict)
    heterogeneous = bool(improvement["heterogeneity"]["heterogeneous"])
    return {
        "estimator": "sequential_flat_prior_paired_delta_v1",
        "contrast": "WDL_PLUS_FULL_CONTEXT_minus_WDL_ONLY_value_mae",
        "improvement_direction": "negative",
        "pools": {
            "C1": _pool_summary(c1, "C1"),
            "C2": _pool_summary(c2, "C2"),
        },
        "posterior_mean_value_mae_delta": -float(posterior["mean"]),
        "posterior_standard_error": float(posterior["standard_error"]),
        "posterior_probability_delta_lt_zero": float(probability["0.00"]),
        "heterogeneity": improvement["heterogeneity"],
        "signal": float(probability["0.00"]) > float(signal_probability)
        and not heterogeneous,
        "may_select_model_or_change_weights": False,
    }
