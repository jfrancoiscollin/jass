"""Train-only C3 diagnostics for the frozen contextual baseline family."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import numpy as np

from .context import COMPONENTS, context_matrix
from .context_gate import exact_pairwise_ordering, spearman_with_ties
from .context_targets import baseline_values


def canonical_fold_ids(
    canonical_ids: np.ndarray,
    *,
    fold_count: int,
    namespace: str,
) -> np.ndarray:
    """Assign all raw views of a canonical state to the same stable fold."""
    ids = np.asarray(canonical_ids, dtype=np.int64)
    if ids.ndim != 1 or not ids.size:
        raise ValueError("C3 canonical IDs must be a non-empty vector")
    if fold_count < 2:
        raise ValueError("C3 requires at least two folds")
    if not namespace:
        raise ValueError("C3 fold namespace must be non-empty")
    cache: dict[int, int] = {}
    folds = np.empty(ids.size, dtype=np.int16)
    for row, canonical_id in enumerate(ids):
        value = int(canonical_id)
        if value not in cache:
            payload = f"{namespace}|{value}".encode("utf-8")
            cache[value] = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % fold_count
        folds[row] = cache[value]
    if set(int(value) for value in np.unique(folds)) != set(range(fold_count)):
        raise ValueError("C3 stable fold assignment produced an empty fold")
    return folds


def _aggregate_contexts(
    contexts: np.ndarray, exact_values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.asarray(contexts, dtype=np.float64)
    values = np.asarray(exact_values, dtype=np.float64)
    unique, inverse = np.unique(matrix, axis=0, return_inverse=True)
    counts = np.bincount(inverse, minlength=unique.shape[0]).astype(np.float64)
    sums = np.bincount(inverse, weights=values, minlength=unique.shape[0])
    return unique, sums / counts, counts


def _weighted_loss(
    matrix: np.ndarray,
    targets: np.ndarray,
    counts: np.ndarray,
    theta: np.ndarray,
    ridge: float,
) -> float:
    residual = np.tanh(matrix @ theta) - targets
    return float(
        0.5 * np.dot(counts, residual * residual) / counts.sum()
        + 0.5 * ridge * np.dot(theta, theta)
    )


def fit_tanh_linear(
    contexts: np.ndarray,
    exact_values: np.ndarray,
    *,
    initial_theta: np.ndarray,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit the odd tanh-linear family with deterministic Gauss-Newton steps."""
    matrix, targets, counts = _aggregate_contexts(contexts, exact_values)
    theta = np.asarray(initial_theta, dtype=np.float64).copy()
    if theta.shape != (len(COMPONENTS),):
        raise ValueError("C3 initial coefficient vector has the wrong shape")
    if ridge < 0.0 or not np.isfinite(ridge):
        raise ValueError("C3 ridge must be finite and non-negative")
    if max_iterations <= 0 or tolerance <= 0.0 or line_search_steps <= 0:
        raise ValueError("C3 optimizer controls must be positive")

    initial_loss = _weighted_loss(matrix, targets, counts, theta, ridge)
    current_loss = initial_loss
    converged = False
    iterations = 0
    identity = np.eye(theta.size, dtype=np.float64)
    total = counts.sum()
    for iteration in range(max_iterations):
        prediction = np.tanh(matrix @ theta)
        derivative = 1.0 - prediction * prediction
        residual = prediction - targets
        weighted_derivative = counts * derivative
        gradient = matrix.T @ (weighted_derivative * residual) / total + ridge * theta
        hessian = (
            matrix.T @ ((counts * derivative * derivative)[:, None] * matrix) / total
            + ridge * identity
            + 1e-12 * identity
        )
        step = np.linalg.solve(hessian, gradient)
        accepted = False
        scale = 1.0
        candidate = theta
        candidate_loss = current_loss
        for _ in range(line_search_steps):
            proposal = theta - scale * step
            proposal_loss = _weighted_loss(matrix, targets, counts, proposal, ridge)
            if proposal_loss < current_loss:
                candidate = proposal
                candidate_loss = proposal_loss
                accepted = True
                break
            scale *= 0.5
        iterations = iteration + 1
        if not accepted:
            break
        update = float(np.max(np.abs(candidate - theta)))
        theta = candidate
        current_loss = candidate_loss
        if update <= tolerance:
            converged = True
            break
    if not np.all(np.isfinite(theta)) or not np.isfinite(current_loss):
        raise RuntimeError("C3 fitted coefficients are non-finite")
    return theta, {
        "unique_context_count": int(matrix.shape[0]),
        "initial_loss": initial_loss,
        "final_loss": current_loss,
        "iterations": iterations,
        "converged": converged,
    }


def _lookup_predictions(
    train_contexts: np.ndarray,
    train_values: np.ndarray,
    evaluation_contexts: np.ndarray,
) -> tuple[np.ndarray, int]:
    matrix, means, _ = _aggregate_contexts(train_contexts, train_values)
    table = {
        np.ascontiguousarray(row).tobytes(): float(value)
        for row, value in zip(matrix, means)
    }
    predictions = np.empty(evaluation_contexts.shape[0], dtype=np.float64)
    unseen = 0
    for index, row in enumerate(np.asarray(evaluation_contexts, dtype=np.float64)):
        key = np.ascontiguousarray(row).tobytes()
        if key in table:
            predictions[index] = table[key]
        else:
            predictions[index] = 0.0
            unseen += 1
    return predictions, unseen


def metric_bundle(predictions: np.ndarray, exact_values: np.ndarray) -> dict[str, Any]:
    predicted = np.asarray(predictions, dtype=np.float64)
    exact = np.asarray(exact_values, dtype=np.int8)
    if predicted.shape != exact.shape or predicted.ndim != 1:
        raise ValueError("C3 metrics require aligned one-dimensional arrays")
    error = predicted - exact.astype(np.float64)
    ordering = exact_pairwise_ordering(predicted, exact)
    return {
        "state_count": int(exact.size),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "spearman": spearman_with_ties(predicted, exact),
        "pairwise_ordering_rate": float(ordering["ordering_rate"]),
        "eligible_pair_count": int(ordering["eligible_pair_count"]),
    }


def run_c3_diagnostic(
    oracle: object,
    split: object,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    protocol = config["c3_diagnostic_v1"]["protocol"]
    if protocol.get("cohort") != "train" or protocol.get("nonterminal_only") is not True:
        raise ValueError("C3 is restricted to non-terminal train states")
    train_ids = np.asarray(getattr(split, "indices")("train"), dtype=np.int64)
    terminal = np.asarray(getattr(oracle, "terminal_status"))[train_ids]
    eligible = train_ids[terminal == 0]
    if not eligible.size:
        raise ValueError("C3 train cohort contains no non-terminal state")
    contexts = context_matrix(oracle, eligible)
    exact = np.asarray(getattr(oracle, "values"))[eligible].astype(np.int8)
    canonical = np.asarray(getattr(oracle, "canonical_ids"))[eligible]

    folds_config = protocol["cross_validation"]
    fold_count = int(folds_config["fold_count"])
    folds = canonical_fold_ids(
        canonical,
        fold_count=fold_count,
        namespace=str(folds_config["namespace"]),
    )
    baseline = config["baseline_v1"]
    handcrafted = baseline_values(contexts, baseline["weights"], float(baseline["tau"]))
    initial_theta = np.asarray(
        [float(baseline["weights"][name]) / float(baseline["tau"]) for name in COMPONENTS],
        dtype=np.float64,
    )
    optimizer = protocol["fitted_tanh_linear"]
    fitted_oof = np.empty(eligible.size, dtype=np.float64)
    lookup_oof = np.empty(eligible.size, dtype=np.float64)
    fold_reports: list[dict[str, Any]] = []
    for fold in range(fold_count):
        evaluation_mask = folds == fold
        training_mask = ~evaluation_mask
        if not np.any(evaluation_mask) or not np.any(training_mask):
            raise ValueError("C3 cross-validation fold is empty")
        if np.intersect1d(
            np.unique(canonical[training_mask]), np.unique(canonical[evaluation_mask])
        ).size:
            raise RuntimeError("C3 canonical class leaked across folds")
        theta, fit = fit_tanh_linear(
            contexts[training_mask],
            exact[training_mask],
            initial_theta=initial_theta,
            ridge=float(optimizer["ridge"]),
            max_iterations=int(optimizer["max_iterations"]),
            tolerance=float(optimizer["tolerance"]),
            line_search_steps=int(optimizer["line_search_steps"]),
        )
        fitted_oof[evaluation_mask] = np.tanh(contexts[evaluation_mask] @ theta)
        lookup, unseen = _lookup_predictions(
            contexts[training_mask], exact[training_mask], contexts[evaluation_mask]
        )
        lookup_oof[evaluation_mask] = lookup
        fold_reports.append(
            {
                "fold": fold,
                "training_state_count": int(np.count_nonzero(training_mask)),
                "evaluation_state_count": int(np.count_nonzero(evaluation_mask)),
                "training_canonical_count": int(np.unique(canonical[training_mask]).size),
                "evaluation_canonical_count": int(np.unique(canonical[evaluation_mask]).size),
                "lookup_unseen_context_count": unseen,
                "fit": fit,
                "fitted_theta": [float(value) for value in theta],
            }
        )

    final_theta, final_fit = fit_tanh_linear(
        contexts,
        exact,
        initial_theta=initial_theta,
        ridge=float(optimizer["ridge"]),
        max_iterations=int(optimizer["max_iterations"]),
        tolerance=float(optimizer["tolerance"]),
        line_search_steps=int(optimizer["line_search_steps"]),
    )
    metrics = {
        "handcrafted": metric_bundle(handcrafted, exact),
        "fitted_tanh_linear_oof": metric_bundle(fitted_oof, exact),
        "context_lookup_oof": metric_bundle(lookup_oof, exact),
    }
    fitted_gain = {
        "spearman_gain": metrics["fitted_tanh_linear_oof"]["spearman"]
        - metrics["handcrafted"]["spearman"],
        "mae_reduction": metrics["handcrafted"]["mae"]
        - metrics["fitted_tanh_linear_oof"]["mae"],
    }
    lookup_gain = {
        "spearman_gain": metrics["context_lookup_oof"]["spearman"]
        - metrics["handcrafted"]["spearman"],
        "mae_reduction": metrics["handcrafted"]["mae"]
        - metrics["context_lookup_oof"]["mae"],
    }
    rule = protocol["interpretation_rule"]
    minimum_spearman = float(rule["minimum_spearman_gain"])
    minimum_mae = float(rule["minimum_mae_reduction"])
    if fitted_gain["spearman_gain"] >= minimum_spearman and fitted_gain["mae_reduction"] >= minimum_mae:
        interpretation = "LINEAR_CALIBRATION_GAP_OBSERVED"
    elif lookup_gain["spearman_gain"] >= minimum_spearman and lookup_gain["mae_reduction"] >= minimum_mae:
        interpretation = "NONLINEAR_MAPPING_GAP_OBSERVED"
    else:
        interpretation = "NO_MATERIAL_TRAIN_ONLY_CONTEXT_GAIN"

    return {
        "schema": "mini_jass.contextual_c3_diagnostic.v1",
        "status": "C3_COMPLETE_DIAGNOSTIC_ONLY",
        "cohort": "train",
        "eligible_state_count": int(eligible.size),
        "eligible_canonical_count": int(np.unique(canonical).size),
        "fold_count": fold_count,
        "canonical_fold_disjointness": True,
        "cohort_reads": {"train": 1, "development": 0, "frozen_test": 0},
        "metrics": metrics,
        "fitted_gain": fitted_gain,
        "lookup_gain": lookup_gain,
        "interpretation": interpretation,
        "folds": fold_reports,
        "final_train_fit": {
            "theta": [float(value) for value in final_theta],
            "equivalent_weights_at_tau_1": {
                name: float(value) for name, value in zip(COMPONENTS, final_theta)
            },
            "fit": final_fit,
        },
        "training_of_c1_or_c2_arms_performed": False,
        "sealed_test_read_count_added": 0,
        "decision_reopened": False,
        "promotable": False,
    }
