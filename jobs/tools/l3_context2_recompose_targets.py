#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recompose certified pure CTX2 predictions at a fixed causal dose.

The expensive CTX2 cross-fit is independent of alpha.  A certified alpha=1
sidecar therefore contains the pure conditional probability.  This tool
authenticates that sidecar, reconstructs the black-POV terminal probability
from the immutable JNNW, and emits aligned and phase/WDL-stratified shuffled
targets at alpha=0.30 without refitting the teacher.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from jobs.tools.l3_conditional_targets import (
        JNNW_DTYPE,
        _atomic_save_npy,
        _atomic_write_json,
        _open_counted,
        _open_meta,
        _sha256,
        game_folds,
        shuffled_within_cohort_folds,
        tempo_phase_from_records,
    )
except ModuleNotFoundError:  # direct execution from jobs/tools
    from l3_conditional_targets import (  # type: ignore[no-redef]
        JNNW_DTYPE,
        _atomic_save_npy,
        _atomic_write_json,
        _open_counted,
        _open_meta,
        _sha256,
        game_folds,
        shuffled_within_cohort_folds,
        tempo_phase_from_records,
    )


def _load_vector(path: Path, count: int, label: str) -> np.ndarray:
    values = np.load(path, allow_pickle=False)
    if values.shape != (count,) or values.dtype != np.float32:
        raise ValueError(
            f"{path}: {label} must be float32 shape ({count},), got "
            f"{values.dtype} {values.shape}"
        )
    if not np.all(np.isfinite(values)) or not np.all((0.0 <= values) & (values <= 1.0)):
        raise ValueError(f"{path}: {label} leaves finite probability range")
    return values


def _moments(values: np.ndarray) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "q01": float(np.quantile(array, 0.01)),
        "q50": float(np.quantile(array, 0.50)),
        "q99": float(np.quantile(array, 0.99)),
        "max": float(np.max(array)),
    }


def _validate_pure_report(
    report: dict[str, Any],
    *,
    count: int,
    train_count: int,
    data_sha: str,
    meta_sha: str,
    pure_sha: str,
) -> None:
    if (
        report.get("schema") != "jass.l3_conditional_targets.v2"
        or report.get("context_schema") != "ctx2-phase-tactical-30"
        or report.get("records") != count
        or report.get("train_records") != train_count
        or report.get("holdout_records") != count - train_count
    ):
        raise ValueError("pure CTX2 report identity/sizing drift")
    target = report.get("target") or {}
    if target.get("alpha") != 1.0 or target.get("output_pov") != "black":
        raise ValueError("source is not a black-POV pure CTX2 alpha=1 sidecar")
    source = report.get("source") or {}
    if source.get("data_sha256") != data_sha or source.get("meta_sha256") != meta_sha:
        raise ValueError("pure CTX2 report corpus hash drift")
    if (report.get("outputs") or {}).get("aligned_sha256") != pure_sha:
        raise ValueError("pure CTX2 sidecar hash differs from its certificate")
    mapping = report.get("mapping") or {}
    fits = [row.get("fit") or {} for row in mapping.get("folds") or []]
    fits.append((mapping.get("final_train_fit") or {}).get("fit") or {})
    if (
        mapping.get("fold_group") != "opening_id"
        or not mapping.get("fold_local_rms")
        or not mapping.get("each_game_total_weight_equal")
        or not mapping.get("all_groups_fold_disjoint")
        or mapping.get("train_holdout_group_overlap") != 0
        or len(fits) != 6
        or not all(row.get("converged") for row in fits)
    ):
        raise ValueError("pure CTX2 strict cross-fit certificate drift")


def run(args: argparse.Namespace) -> dict[str, Any]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    pure_path = Path(args.pure_context_target)
    pure_report_path = Path(args.pure_context_report)
    aligned_path = Path(args.aligned_out)
    shuffled_path = Path(args.shuffled_out)
    report_path = Path(args.report)
    reference_path = Path(args.reference_target) if args.reference_target else None
    reference_report_path = (
        Path(args.reference_report) if args.reference_report else None
    )
    input_paths = {data_path, meta_path, pure_path, pure_report_path}
    if reference_path:
        input_paths.add(reference_path)
    if reference_report_path:
        input_paths.add(reference_report_path)
    output_paths = {aligned_path, shuffled_path, report_path}
    if len(output_paths) != 3 or input_paths & output_paths:
        raise ValueError("outputs must be distinct and cannot alias inputs")
    if any(path.exists() for path in output_paths):
        raise ValueError("recomposed outputs are no-clobber")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    count = len(records)
    train_count = int(args.train_count)
    if not 0 < train_count < count:
        raise ValueError("--train-count must leave non-empty train and holdout")
    alpha = float(args.alpha)
    if not 0.0 < alpha < 1.0:
        raise ValueError("--alpha must be strictly between zero and one")
    phase_bins_count = int(args.shuffle_phase_bins)
    if phase_bins_count < 2:
        raise ValueError("--shuffle-phase-bins must be >=2")

    data_sha = _sha256(data_path)
    meta_sha = _sha256(meta_path)
    pure_sha = _sha256(pure_path)
    pure_report = json.loads(pure_report_path.read_text(encoding="utf-8"))
    _validate_pure_report(
        pure_report,
        count=count,
        train_count=train_count,
        data_sha=data_sha,
        meta_sha=meta_sha,
        pure_sha=pure_sha,
    )
    pure = _load_vector(pure_path, count, "pure CTX2 target")

    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    if not np.all(np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("JNNW contains WDL outside {-1,0,1}")
    terminal = (outcomes + 1.0) * 0.5
    opening_ids = np.asarray(metadata["opening_id"], dtype=np.uint64)
    if np.intersect1d(
        np.unique(opening_ids[:train_count]),
        np.unique(opening_ids[train_count:]),
        assume_unique=True,
    ).size:
        raise ValueError("opening_id leaks across train/holdout")
    folds = game_folds(opening_ids, int(args.fold_count), int(args.fold_seed))
    phase = tempo_phase_from_records(records)
    phase_bins = np.minimum(
        np.floor(phase * phase_bins_count).astype(np.int16),
        phase_bins_count - 1,
    )
    wdl_codes = np.asarray(outcomes + 1.0, dtype=np.int16)
    strata = wdl_codes * phase_bins_count + phase_bins
    shuffled_pure, shuffle_report = shuffled_within_cohort_folds(
        pure,
        folds,
        train_count,
        int(args.shuffle_seed),
        strata,
        f"terminal_wdl_black_x_tempo_phase_{phase_bins_count}_bins",
    )
    # Release Windows memmap handles before any fail-closed diagnostic raises.
    del metadata, records

    aligned = np.asarray((1.0 - alpha) * terminal + alpha * pure, dtype=np.float32)
    shuffled = np.asarray(
        (1.0 - alpha) * terminal + alpha * shuffled_pure,
        dtype=np.float32,
    )
    if not np.all((0.0 <= aligned) & (aligned <= 1.0)):
        raise RuntimeError("aligned target left probability range")
    if not np.all((0.0 <= shuffled) & (shuffled <= 1.0)):
        raise RuntimeError("shuffled target left probability range")
    for start, stop in ((0, train_count), (train_count, count)):
        for fold in np.unique(folds[start:stop]):
            for stratum in np.unique(strata[start:stop]):
                members = (
                    np.flatnonzero(
                        (folds[start:stop] == fold)
                        & (strata[start:stop] == stratum)
                    )
                    + start
                )
                if not np.allclose(
                    np.sort(aligned[members]),
                    np.sort(shuffled[members]),
                    rtol=0.0,
                    atol=1e-7,
                ):
                    raise RuntimeError("shuffle changed a final target marginal")

    comparison: dict[str, Any] | None = None
    if (reference_path is None) != (reference_report_path is None):
        raise ValueError("--reference-target and --reference-report are paired")
    if reference_path and reference_report_path:
        reference = _load_vector(reference_path, count, "CTX1 alpha=0.30 reference")
        reference_report = json.loads(
            reference_report_path.read_text(encoding="utf-8")
        )
        if (
            reference_report.get("records") != count
            or reference_report.get("train_records") != train_count
            or (reference_report.get("target") or {}).get("alpha") != alpha
            or (reference_report.get("outputs") or {}).get("aligned_sha256")
            != _sha256(reference_path)
        ):
            raise ValueError("CTX1 alpha=0.30 reference certificate drift")
        reference_std = float(np.std(reference, dtype=np.float64))
        comparison = {
            "reference_schema": reference_report.get("context_schema"),
            "reference_sha256": _sha256(reference_path),
            "aligned_max_abs_delta": float(
                np.max(np.abs(aligned.astype(np.float64) - reference))
            ),
            "aligned_mean_delta": float(
                np.mean(aligned.astype(np.float64) - reference)
            ),
            "aligned_std_ratio": float(
                np.std(aligned, dtype=np.float64) / reference_std
            ),
            "shuffled_std_ratio": float(
                np.std(shuffled, dtype=np.float64) / reference_std
            ),
        }

    _atomic_save_npy(aligned_path, aligned)
    _atomic_save_npy(shuffled_path, shuffled)
    report = {
        "schema": "jass.l3_context2_recomposed_targets.v1",
        "operation": "authenticate_pure_ctx2_then_recompose",
        "records": count,
        "train_records": train_count,
        "holdout_records": count - train_count,
        "meta_schema": meta_schema,
        "target": {
            "formula": "(1-alpha)*terminal_probability_black+alpha*pure_ctx2_probability_black",
            "alpha": alpha,
            "output_pov": "black",
            "output_range": "win_probability_[0,1]",
        },
        "strict_protocol": {
            "fold_group": "opening_id",
            "fold_count": int(args.fold_count),
            "fold_seed": int(args.fold_seed),
            "shuffle_seed": int(args.shuffle_seed),
            "shuffle_stratification": (
                f"terminal_wdl_black_x_tempo_phase_{phase_bins_count}_bins"
            ),
            "train_holdout_opening_overlap": 0,
            **shuffle_report,
            "all_final_target_marginals_preserved": True,
        },
        "source": {
            "data_sha256": data_sha,
            "meta_sha256": meta_sha,
            "pure_context_target_sha256": pure_sha,
            "pure_context_report_sha256": _sha256(pure_report_path),
            "pure_context_schema": pure_report.get("context_schema"),
            "pure_context_alpha": (pure_report.get("target") or {}).get("alpha"),
        },
        "moments": {
            "terminal": _moments(terminal),
            "pure_ctx2": _moments(pure),
            "aligned_alpha30": _moments(aligned),
            "shuffled_alpha30": _moments(shuffled),
        },
        "reference_ctx1_alpha30": comparison,
    }
    report["outputs"] = {
        "aligned": str(aligned_path),
        "aligned_sha256": "",
        "shuffled": str(shuffled_path),
        "shuffled_sha256": "",
    }
    report["outputs"]["aligned_sha256"] = _sha256(aligned_path)
    report["outputs"]["shuffled_sha256"] = _sha256(shuffled_path)
    _atomic_write_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--pure-context-target", required=True)
    parser.add_argument("--pure-context-report", required=True)
    parser.add_argument("--train-count", required=True, type=int)
    parser.add_argument("--aligned-out", required=True)
    parser.add_argument("--shuffled-out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--reference-target")
    parser.add_argument("--reference-report")
    parser.add_argument("--alpha", type=float, default=0.30)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=20260812)
    parser.add_argument("--shuffle-phase-bins", type=int, default=4)
    args = parser.parse_args(argv)
    print(json.dumps(run(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
