#!/usr/bin/env python3
"""Attribute a certified CTX2 target on one immutable, fixed corpus.

The conditional teacher is tanh-linear, but its train-prefix predictions are
out-of-fold.  This audit therefore replays the exact fold-local raw
coefficients for train rows and the final-train coefficients for holdout rows.
It reports both additive pre-tanh logit contributions and non-additive
leave-one-component-out effects on the final alpha-dosed probability target.
No mapper or PatternEval is fitted here.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:  # Script execution (jobs/tools is sys.path[0]).
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        game_folds,
    )
except ModuleNotFoundError:  # Package import from repository tests.
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        game_folds,
    )


def _new_accumulator(width: int, base_width: int) -> dict[str, Any]:
    return {
        "rows": 0,
        "weight_sum": 0.0,
        "linear_sum": np.zeros(width),
        "linear_abs_sum": np.zeros(width),
        "linear_sq_sum": np.zeros(width),
        "linear_local_sum": np.zeros(width),
        "linear_local_abs_sum": np.zeros(width),
        "linear_local_sq_sum": np.zeros(width),
        "linear_dominant_weight": np.zeros(width),
        "linear_abs_total_sum": 0.0,
        "base_sum": np.zeros(base_width),
        "base_abs_sum": np.zeros(base_width),
        "base_sq_sum": np.zeros(base_width),
        "base_local_sum": np.zeros(base_width),
        "base_local_abs_sum": np.zeros(base_width),
        "base_local_sq_sum": np.zeros(base_width),
        "base_dominant_weight": np.zeros(base_width),
        "base_abs_total_sum": 0.0,
        "base_cross": np.zeros((base_width, base_width)),
        "base_outcome_cross": np.zeros(base_width),
        "base_prediction_cross": np.zeros(base_width),
        "outcome_sum": 0.0,
        "outcome_sq_sum": 0.0,
        "prediction_sum": 0.0,
        "prediction_sq_sum": 0.0,
        "target_shift_sum": 0.0,
        "target_shift_abs_sum": 0.0,
        "target_shift_sq_sum": 0.0,
        "saturated_weight": 0.0,
    }


def _update(
    acc: dict[str, Any],
    linear: np.ndarray,
    local: np.ndarray,
    base_linear: np.ndarray,
    base_local: np.ndarray,
    weights: np.ndarray,
    outcomes: np.ndarray,
    predictions: np.ndarray,
    target_shift: np.ndarray,
) -> None:
    if not len(weights):
        return
    weight_sum = float(weights.sum())
    acc["rows"] += int(len(weights))
    acc["weight_sum"] += weight_sum
    acc["linear_sum"] += linear.T @ weights
    acc["linear_abs_sum"] += np.abs(linear).T @ weights
    acc["linear_sq_sum"] += (linear * linear).T @ weights
    acc["linear_local_sum"] += local.T @ weights
    acc["linear_local_abs_sum"] += np.abs(local).T @ weights
    acc["linear_local_sq_sum"] += (local * local).T @ weights
    acc["linear_dominant_weight"] += np.bincount(
        np.argmax(np.abs(linear), axis=1), weights=weights, minlength=linear.shape[1]
    )
    acc["linear_abs_total_sum"] += float(np.sum(weights * np.abs(linear).sum(axis=1)))

    acc["base_sum"] += base_linear.T @ weights
    acc["base_abs_sum"] += np.abs(base_linear).T @ weights
    acc["base_sq_sum"] += (base_linear * base_linear).T @ weights
    acc["base_local_sum"] += base_local.T @ weights
    acc["base_local_abs_sum"] += np.abs(base_local).T @ weights
    acc["base_local_sq_sum"] += (base_local * base_local).T @ weights
    acc["base_dominant_weight"] += np.bincount(
        np.argmax(np.abs(base_linear), axis=1),
        weights=weights,
        minlength=base_linear.shape[1],
    )
    acc["base_abs_total_sum"] += float(
        np.sum(weights * np.abs(base_linear).sum(axis=1))
    )
    acc["base_cross"] += base_linear.T @ (base_linear * weights[:, None])
    acc["base_outcome_cross"] += base_linear.T @ (outcomes * weights)
    acc["base_prediction_cross"] += base_linear.T @ (predictions * weights)
    acc["outcome_sum"] += float(outcomes @ weights)
    acc["outcome_sq_sum"] += float((outcomes * outcomes) @ weights)
    acc["prediction_sum"] += float(predictions @ weights)
    acc["prediction_sq_sum"] += float((predictions * predictions) @ weights)
    acc["target_shift_sum"] += float(target_shift @ weights)
    acc["target_shift_abs_sum"] += float(np.abs(target_shift) @ weights)
    acc["target_shift_sq_sum"] += float((target_shift * target_shift) @ weights)
    acc["saturated_weight"] += float(weights[np.abs(predictions) >= 0.95].sum())


def _correlation(cross: float, left_sum: float, left_sq: float,
                 right_sum: float, right_sq: float, weight: float) -> float | None:
    left_var = max(left_sq / weight - (left_sum / weight) ** 2, 0.0)
    right_var = max(right_sq / weight - (right_sum / weight) ** 2, 0.0)
    denom = math.sqrt(left_var * right_var)
    if denom <= 1e-15:
        return None
    return float((cross / weight - left_sum * right_sum / (weight * weight)) / denom)


def _component_rows(
    names: tuple[str, ...],
    acc: dict[str, Any],
    prefix: str,
    coefficient_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    weight = acc["weight_sum"]
    abs_sum = acc[f"{prefix}_abs_sum"]
    total = acc[f"{prefix}_abs_total_sum"]
    rows = []
    for index, name in enumerate(names):
        row = {
            "component": name,
            "mean_signed_logit_contribution": float(acc[f"{prefix}_sum"][index] / weight),
            "mean_absolute_logit_contribution": float(abs_sum[index] / weight),
            "rms_logit_contribution": float(math.sqrt(acc[f"{prefix}_sq_sum"][index] / weight)),
            "absolute_logit_share": float(abs_sum[index] / total) if total else 0.0,
            "dominant_position_rate": float(acc[f"{prefix}_dominant_weight"][index] / weight),
            "mean_signed_alpha_target_probability_effect": float(
                acc[f"{prefix}_local_sum"][index] / weight
            ),
            "mean_absolute_alpha_target_probability_effect": float(
                acc[f"{prefix}_local_abs_sum"][index] / weight
            ),
            "rms_alpha_target_probability_effect": float(
                math.sqrt(acc[f"{prefix}_local_sq_sum"][index] / weight)
            ),
        }
        if coefficient_rows is not None:
            values = [float(item["theta_raw"][index]) for item in coefficient_rows]
            nonzero = [math.copysign(1.0, value) for value in values if abs(value) > 1e-15]
            row["raw_coefficients_by_mapper"] = values
            row["raw_coefficient_min"] = min(values)
            row["raw_coefficient_max"] = max(values)
            row["raw_coefficient_sign_consistent"] = len(set(nonzero)) <= 1
        rows.append(row)
    return rows


def _finalize(acc: dict[str, Any], mapper_rows: list[dict[str, Any]]) -> dict[str, Any]:
    weight = acc["weight_sum"]
    raw = _component_rows(CTX2_CONTEXT_COMPONENTS, acc, "linear", mapper_rows)
    # Alias the accumulator keys expected by the generic formatter.
    base_view = dict(acc)
    base_view["base_abs_total_sum"] = acc["base_abs_total_sum"]
    base = _component_rows(CTX2_BASE_COMPONENTS, base_view, "base")

    base_mean = acc["base_sum"] / weight
    base_cov = acc["base_cross"] / weight - np.outer(base_mean, base_mean)
    base_cov = 0.5 * (base_cov + base_cov.T)
    variance = np.maximum(np.diag(base_cov), 0.0)
    denom = np.sqrt(np.outer(variance, variance))
    corr = np.divide(base_cov, denom, out=np.zeros_like(base_cov), where=denom > 1e-18)
    np.fill_diagonal(corr, np.where(variance > 1e-18, 1.0, 0.0))
    high_pairs = []
    for left in range(len(CTX2_BASE_COMPONENTS)):
        for right in range(left + 1, len(CTX2_BASE_COMPONENTS)):
            value = float(corr[left, right])
            if abs(value) >= 0.90:
                high_pairs.append({
                    "left": CTX2_BASE_COMPONENTS[left],
                    "right": CTX2_BASE_COMPONENTS[right],
                    "r": value,
                })
    for index, row in enumerate(base):
        row["correlation_with_terminal_outcome"] = _correlation(
            acc["base_outcome_cross"][index], acc["base_sum"][index],
            acc["base_sq_sum"][index], acc["outcome_sum"], acc["outcome_sq_sum"], weight,
        )
        row["correlation_with_conditional_prediction"] = _correlation(
            acc["base_prediction_cross"][index], acc["base_sum"][index],
            acc["base_sq_sum"][index], acc["prediction_sum"], acc["prediction_sq_sum"], weight,
        )

    raw_shares = np.asarray([row["absolute_logit_share"] for row in raw])
    base_shares = np.asarray([row["absolute_logit_share"] for row in base])
    return {
        "rows": acc["rows"],
        "effective_game_equal_weight_sum": weight,
        "conditional_prediction_saturation_rate_abs_ge_0_95": acc["saturated_weight"] / weight,
        "alpha_target_probability_shift": {
            "mean_signed": acc["target_shift_sum"] / weight,
            "mean_absolute": acc["target_shift_abs_sum"] / weight,
            "rms": math.sqrt(acc["target_shift_sq_sum"] / weight),
        },
        "phase_bank_absolute_logit_share": {
            "tempo_mid": float(raw_shares[:15].sum()),
            "tempo_end": float(raw_shares[15:].sum()),
        },
        "raw_30_components": raw,
        "base_15_components": base,
        "raw_30_concentration": {
            "largest_share": float(raw_shares.max()),
            "top3_share": float(np.sort(raw_shares)[-3:].sum()),
            "effective_component_count": float(1.0 / np.sum(raw_shares * raw_shares)),
        },
        "base_15_concentration": {
            "largest_share": float(base_shares.max()),
            "top3_share": float(np.sort(base_shares)[-3:].sum()),
            "effective_component_count": float(1.0 / np.sum(base_shares * base_shares)),
        },
        "base_contribution_correlation": {
            "matrix": [[float(value) for value in row] for row in corr],
            "high_absolute_pairs_ge_0_90": high_pairs,
        },
    }


def audit(
    *,
    data_path: Path,
    meta_path: Path,
    feat_path: Path,
    aligned_target_path: Path,
    conditional_report_path: Path,
    chunk_size: int = 20_000,
) -> dict[str, Any]:
    report = json.loads(conditional_report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "jass.l3_conditional_targets.v2":
        raise ValueError("conditional report schema drift")
    if report.get("context_schema") != "ctx2-phase-tactical-30":
        raise ValueError("audit requires CTX2 phase-tactical report")
    mapping = report.get("mapping") or {}
    if (
        mapping.get("fold_group") != "opening_id"
        or mapping.get("row_weighting") != "game_equal"
        or not mapping.get("fold_local_rms")
        or not mapping.get("each_game_total_weight_equal")
    ):
        raise ValueError("strict CTX2 mapping contract drift")
    alpha = float((report.get("target") or {}).get("alpha", 0.0))
    if not 0.0 < alpha <= 1.0:
        raise ValueError("invalid conditional target alpha")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    if width != len(CTX2_CONTEXT_COMPONENTS):
        raise ValueError("CTX2 feature width drift")
    train_count = int(report.get("train_records", -1))
    if (report.get("records"), report.get("holdout_records")) != (
        len(records), len(records) - train_count
    ):
        raise ValueError("conditional report sizing drift")
    source = report.get("source") or {}
    expected_hashes = {
        "data": _sha256(data_path),
        "meta": _sha256(meta_path),
        "feat": _sha256(feat_path),
    }
    for key, digest in expected_hashes.items():
        if source.get(f"{key}_sha256") != digest:
            raise ValueError(f"conditional source {key} hash drift")

    # The target vector is only 4 bytes per position; loading it closes the file
    # immediately and also avoids Windows memmap handles surviving test errors.
    aligned = np.load(aligned_target_path, allow_pickle=False)
    if aligned.shape != (len(records),) or aligned.dtype != np.float32:
        raise ValueError("aligned target shape/dtype drift")
    if (report.get("outputs") or {}).get("aligned_sha256") != _sha256(aligned_target_path):
        raise ValueError("aligned target hash drift")

    components = tuple(mapping.get("components") or ())
    if components != CTX2_CONTEXT_COMPONENTS:
        raise ValueError("CTX2 component order drift")
    fold_count = int(mapping.get("fold_count", 0))
    fold_seed = int(mapping.get("fold_seed", -1))
    fold_reports = sorted(mapping.get("folds") or [], key=lambda row: int(row["fold"]))
    if len(fold_reports) != fold_count or [int(row["fold"]) for row in fold_reports] != list(range(fold_count)):
        raise ValueError("conditional fold report drift")
    mapper_rows = [
        {"label": f"oof_fold_{row['fold']}", "theta_raw": row["theta_raw"]}
        for row in fold_reports
    ] + [{
        "label": "final_train_for_holdout",
        "theta_raw": mapping["final_train_fit"]["theta_raw"],
    }]
    coefficient_table = np.asarray([row["theta_raw"] for row in mapper_rows], dtype=np.float64)
    if coefficient_table.shape != (fold_count + 1, width) or not np.all(np.isfinite(coefficient_table)):
        raise ValueError("conditional coefficient table drift")
    folds = game_folds(np.asarray(metadata["opening_id"], dtype=np.uint64), fold_count, fold_seed)
    weights = _game_equal_weights(np.asarray(metadata["game_id"], dtype=np.uint64))

    accs = {
        "all": _new_accumulator(width, len(CTX2_BASE_COMPONENTS)),
        "train_oof": _new_accumulator(width, len(CTX2_BASE_COMPONENTS)),
        "holdout_final_mapper": _new_accumulator(width, len(CTX2_BASE_COMPONENTS)),
    }
    recovery_max = 0.0
    for start in range(0, len(records), chunk_size):
        stop = min(start + chunk_size, len(records))
        x = np.asarray(features[start:stop], dtype=np.float64)
        model_ids = np.asarray(folds[start:stop], dtype=np.int64)
        if stop > train_count:
            model_ids[max(train_count - start, 0):] = fold_count
        linear = x * coefficient_table[model_ids]
        logits = linear.sum(axis=1)
        predictions = np.tanh(logits)
        outcomes = np.asarray(
            np.where(records["stm"][start:stop] == 1,
                     records["wdl"][start:stop], -records["wdl"][start:stop]),
            dtype=np.float64,
        )
        target_probability = np.asarray(aligned[start:stop], dtype=np.float64)
        observed_prediction = ((2.0 * target_probability - 1.0) - (1.0 - alpha) * outcomes) / alpha
        recovery_max = max(recovery_max, float(np.max(np.abs(predictions - observed_prediction))))
        local = 0.5 * alpha * (
            predictions[:, None] - np.tanh(logits[:, None] - linear)
        )
        base_linear = linear[:, :15] + linear[:, 15:]
        base_local = 0.5 * alpha * (
            predictions[:, None] - np.tanh(logits[:, None] - base_linear)
        )
        target_shift = target_probability - 0.5 * (outcomes + 1.0)
        w = weights[start:stop]
        split = min(max(train_count - start, 0), stop - start)
        masks = {
            "all": slice(None),
            "train_oof": slice(0, split),
            "holdout_final_mapper": slice(split, stop - start),
        }
        for name, selection in masks.items():
            _update(
                accs[name], linear[selection], local[selection], base_linear[selection],
                base_local[selection], w[selection], outcomes[selection],
                predictions[selection], target_shift[selection],
            )
    if recovery_max > 2e-6:
        raise RuntimeError(f"conditional prediction recovery drift: {recovery_max}")

    cohorts = {name: _finalize(acc, mapper_rows) for name, acc in accs.items()}
    train_base = cohorts["train_oof"]["base_15_components"]
    train_raw = cohorts["train_oof"]["raw_30_components"]
    return {
        "schema": "jass.l3_context2_fixed_contribution_audit.v1",
        "verdict": "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY",
        "protocol": {
            "same_fixed_positions": True,
            "new_selfplay_generated": False,
            "mapper_refit": False,
            "patterneval_fit": False,
            "fold_local_oof_coefficients_replayed": True,
            "holdout_uses_final_train_mapper": True,
            "row_weighting": "game_equal",
            "local_effect_definition": "alpha/2*(tanh(z)-tanh(z-z_component)); non-additive",
        },
        "source": {
            "records": len(records),
            "train_records": train_count,
            "holdout_records": len(records) - train_count,
            "meta_schema": meta_schema,
            "data_sha256": expected_hashes["data"],
            "meta_sha256": expected_hashes["meta"],
            "feat_sha256": expected_hashes["feat"],
            "aligned_target_sha256": _sha256(aligned_target_path),
            "conditional_report_sha256": _sha256(conditional_report_path),
            "alpha": alpha,
            "fold_count": fold_count,
            "fold_seed": fold_seed,
        },
        "prediction_recovery_max_absolute_error": recovery_max,
        "cohorts": cohorts,
        "train_oof_rankings": {
            "base_by_mean_absolute_target_effect": [
                row["component"] for row in sorted(
                    train_base,
                    key=lambda row: row["mean_absolute_alpha_target_probability_effect"],
                    reverse=True,
                )
            ],
            "raw_by_mean_absolute_target_effect": [
                row["component"] for row in sorted(
                    train_raw,
                    key=lambda row: row["mean_absolute_alpha_target_probability_effect"],
                    reverse=True,
                )
            ],
            "raw_coefficient_sign_flip_components": [
                row["component"] for row in train_raw
                if not row["raw_coefficient_sign_consistent"]
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--feat", type=Path, required=True)
    parser.add_argument("--aligned-target", type=Path, required=True)
    parser.add_argument("--conditional-report", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=20_000)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    payload = audit(
        data_path=args.data,
        meta_path=args.meta,
        feat_path=args.feat,
        aligned_target_path=args.aligned_target,
        conditional_report_path=args.conditional_report,
        chunk_size=args.chunk_size,
    )
    if args.report.exists():
        raise ValueError(f"{args.report}: output exists (no-clobber)")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
