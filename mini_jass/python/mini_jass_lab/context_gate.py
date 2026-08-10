"""Fail-closed C0 protocol-validity gate for contextual supervision."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from .context import (
    COMPONENTS,
    context_matrix,
    context_vector,
    feature_definition_hash,
    rotate180_and_swap_colours,
    state_from_oracle,
    terminal_status,
)
from .context_targets import baseline_values


def digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _average_ranks(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    order = np.argsort(data, kind="mergesort")
    sorted_values = data[order]
    ranks = np.empty(data.size, dtype=np.float64)
    start = 0
    while start < data.size:
        end = start + 1
        while end < data.size and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + end - 1) + 1.0
        start = end
    return ranks


def spearman_with_ties(lhs: np.ndarray, rhs: np.ndarray) -> float:
    left = _average_ranks(np.asarray(lhs))
    right = _average_ranks(np.asarray(rhs))
    left -= left.mean()
    right -= right.mean()
    denominator = float(np.sqrt(np.dot(left, left) * np.dot(right, right)))
    if denominator == 0.0:
        raise ValueError("Spearman correlation is undefined for a constant input")
    return float(np.dot(left, right) / denominator)


def exact_pairwise_ordering(
    baseline: np.ndarray,
    exact_values: np.ndarray,
    *,
    tie_credit: float = 0.5,
) -> dict[str, int | float]:
    if float(tie_credit) != 0.5:
        raise ValueError("C0 exact rank counting currently requires half tie credit")
    predictions = np.asarray(baseline, dtype=np.float64)
    outcomes = np.asarray(exact_values, dtype=np.int8)
    if predictions.shape != outcomes.shape or predictions.ndim != 1:
        raise ValueError("pairwise inputs must be aligned one-dimensional arrays")
    if np.any(~np.isin(outcomes, (-1, 0, 1))):
        raise ValueError("exact values must use the frozen WDL vocabulary")

    wins = 0
    ties = 0
    pair_count = 0
    for lower_value, higher_value in ((-1, 0), (-1, 1), (0, 1)):
        lower = np.sort(predictions[outcomes == lower_value])
        higher = predictions[outcomes == higher_value]
        if not lower.size or not higher.size:
            continue
        less = np.searchsorted(lower, higher, side="left")
        less_or_equal = np.searchsorted(lower, higher, side="right")
        wins += int(less.sum(dtype=np.int64))
        ties += int((less_or_equal - less).sum(dtype=np.int64))
        pair_count += int(lower.size) * int(higher.size)
    if pair_count == 0:
        raise ValueError("C0 train cohort contains no unequal exact-value pair")
    score = (2 * wins + ties) / (2 * pair_count)
    return {
        "eligible_pair_count": pair_count,
        "correct_order_count": wins,
        "baseline_tie_count": ties,
        "ordering_rate": float(score),
    }


def evaluate_c0(
    oracle: object,
    split: object,
    config: dict[str, Any],
) -> dict[str, Any]:
    if config.get("schema") != "mini_jass.contextual_outcome_supervision.v3":
        raise ValueError("C0 requires the frozen contextual v3 contract")
    expected_split_hash = config["data_contract"]["split_manifest_hash"]
    split_manifest = getattr(split, "manifest")
    if split_manifest.get("manifest_hash") != expected_split_hash:
        raise ValueError("C0 split manifest differs from the frozen pin")
    cohort = config["c0_gate"]["oracle_characterization_cohort"]
    if cohort != "train":
        raise ValueError("C0 oracle characterization is restricted to train")
    actual_feature_hash = feature_definition_hash()
    if config["context_v1"].get("feature_definition_hash") != actual_feature_hash:
        raise ValueError("C0 feature definition differs from the frozen pin")
    train_ids = np.asarray(getattr(split, "indices")("train"), dtype=np.int64)
    if train_ids.size == 0:
        raise ValueError("C0 train cohort is empty")

    first = context_matrix(oracle, train_ids)
    second = context_matrix(oracle, train_ids)
    repeatable = bool(np.array_equal(first, second))
    symmetry_error = 0.0
    rule_status = np.empty(train_ids.size, dtype=np.uint8)
    for row, state_id in enumerate(train_ids):
        state = state_from_oracle(oracle, int(state_id))
        transformed = rotate180_and_swap_colours(state)
        image = context_vector(transformed)
        symmetry_error = max(symmetry_error, float(np.max(np.abs(first[row] - image))))
        rule_status[row] = terminal_status(state)

    oracle_status = np.asarray(getattr(oracle, "terminal_status"))[train_ids]
    if not np.array_equal(rule_status, oracle_status):
        raise ValueError("C0 Python context rules disagree with the frozen oracle")
    expected_terminal = np.where(oracle_status == 1, -1.0, 0.0)
    terminal_column = first[:, COMPONENTS.index("terminal_flag")]
    terminal_exactness = float(np.mean(terminal_column == expected_terminal))

    baseline_config = config["baseline_v1"]
    baseline = baseline_values(
        first,
        baseline_config["weights"],
        float(baseline_config["tau"]),
    )
    exact = np.asarray(getattr(oracle, "values"))[train_ids]
    spearman = spearman_with_ties(baseline, exact)
    ordering = exact_pairwise_ordering(
        baseline,
        exact,
        tie_credit=float(config["c0_gate"]["pairwise_ordering"]["baseline_tie_credit"]),
    )
    required = config["c0_gate"]["required"]
    checks = {
        "deterministic_repeatability_exact": repeatable,
        "pov_symmetry_maximum_absolute_error": symmetry_error,
        "context_terminal_flag_exactness_rate": terminal_exactness,
        "baseline_spearman_vs_exact_value": spearman,
        "baseline_pairwise_ordering_rate": ordering["ordering_rate"],
    }
    passed = (
        repeatable == bool(required["deterministic_repeatability_exact"])
        and symmetry_error <= float(required["pov_symmetry_maximum_absolute_error"])
        and terminal_exactness
        >= float(required["context_terminal_flag_exactness_rate"])
        and spearman >= float(required["minimum_baseline_spearman_vs_exact_value"])
        and float(ordering["ordering_rate"])
        >= float(required["minimum_baseline_pairwise_ordering_rate"])
    )
    baseline_definition = {
        "weights": {
            name: float(baseline_config["weights"][name]) for name in COMPONENTS
        },
        "tau": float(baseline_config["tau"]),
        "residual_clip": float(baseline_config["residual_clip"]),
    }
    baseline_hash = digest(baseline_definition)
    if baseline_config.get("definition_hash") != baseline_hash:
        raise ValueError("C0 baseline definition differs from the frozen pin")
    report: dict[str, Any] = {
        "schema": "mini_jass.contextual_c0_gate.v1",
        "status": "PASS" if passed else config["c0_gate"]["on_failure"],
        "cohort": "train",
        "train_state_count": int(train_ids.size),
        "split_manifest_hash": expected_split_hash,
        "feature_definition_hash": actual_feature_hash,
        "baseline_definition_hash": baseline_hash,
        "checks": checks,
        "pairwise_ordering": ordering,
        "sealed_test_read": False,
        "c1_training_authorized": bool(passed),
    }
    report["report_hash"] = digest(report)
    return report


def attach_export_proof(
    report: dict[str, Any],
    proof: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Attach the full-oracle scalar-export proof and preserve fail closure."""
    updated = dict(report)
    updated.pop("report_hash", None)
    updated["implementation_proof"] = dict(proof)
    export = config["training_scaffold_v1"]["export"]
    proof_pass = (
        float(proof["maximum_absolute_value_error"])
        <= float(export["maximum_absolute_value_error"])
        and float(proof["common_search_action_match_rate"])
        >= float(export["required_common_search_action_match_rate"])
        and proof.get("value_error_pass") is True
        and proof.get("action_match_pass") is True
    )
    if not proof_pass:
        updated["status"] = config["c0_gate"]["on_failure"]
        updated["c1_training_authorized"] = False
    updated["report_hash"] = digest(updated)
    return updated
