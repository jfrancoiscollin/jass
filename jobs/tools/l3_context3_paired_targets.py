#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compose paired CTX3 aligned and causally shuffled PatternEval targets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import (
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
except ModuleNotFoundError:
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


def compose_targets(
    predictions: np.ndarray,
    outcomes: np.ndarray,
    folds: np.ndarray,
    strata: np.ndarray,
    train_count: int,
    *,
    alpha: float,
    shuffle_seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    prediction = np.asarray(predictions, dtype=np.float64)
    outcome = np.asarray(outcomes, dtype=np.float64)
    if prediction.shape != outcome.shape or folds.shape != outcome.shape or strata.shape != outcome.shape:
        raise ValueError("CTX3 paired-target inputs are not aligned")
    if not 0 < train_count < len(outcome):
        raise ValueError("train_count must leave a holdout")
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0,1]")
    if not np.all(np.isfinite(prediction)) or np.any(np.abs(prediction) > 1.0):
        raise ValueError("CTX3 predictions left finite WDL range")
    shuffled_prediction, shuffle_report = shuffled_within_cohort_folds(
        prediction,
        folds,
        train_count,
        shuffle_seed,
        strata,
        "terminal_wdl_black_x_tempo_phase_4_bins",
    )
    aligned_wdl = (1.0 - alpha) * outcome + alpha * prediction
    shuffled_wdl = (1.0 - alpha) * outcome + alpha * shuffled_prediction
    aligned = np.asarray((aligned_wdl + 1.0) * 0.5, dtype=np.float32)
    shuffled = np.asarray((shuffled_wdl + 1.0) * 0.5, dtype=np.float32)
    if not (
        np.all(np.isfinite(aligned))
        and np.all(np.isfinite(shuffled))
        and np.all((0.0 <= aligned) & (aligned <= 1.0))
        and np.all((0.0 <= shuffled) & (shuffled <= 1.0))
    ):
        raise RuntimeError("CTX3 paired target left black-POV probability range")
    marginals_preserved = True
    for start, stop in ((0, train_count), (train_count, len(outcome))):
        for fold in np.unique(folds[start:stop]):
            for stratum in np.unique(strata[start:stop]):
                members = np.flatnonzero(
                    (folds[start:stop] == fold) & (strata[start:stop] == stratum)
                ) + start
                if not np.array_equal(np.sort(aligned[members]), np.sort(shuffled[members])):
                    marginals_preserved = False
                    break
    if not marginals_preserved:
        raise RuntimeError("CTX3 paired-target shuffle changed a causal-stratum marginal")
    shuffle_report["all_final_target_marginals_preserved"] = True
    return aligned, shuffled, shuffle_report


def run(args: argparse.Namespace) -> dict[str, Any]:
    data_path, meta_path = Path(args.data), Path(args.meta)
    prediction_path, mapper_report_path = Path(args.prediction), Path(args.mapper_report)
    aligned_path, shuffled_path, report_path = (
        Path(args.aligned_out), Path(args.shuffled_out), Path(args.report)
    )
    if any(path.exists() for path in (aligned_path, shuffled_path, report_path)):
        raise ValueError("CTX3 paired-target outputs are no-clobber")
    mapper = json.loads(mapper_report_path.read_text(encoding="utf-8"))
    if mapper.get("schema") != "jass.l3_context3_exact_tanh_mapper_screen.v1":
        raise ValueError("1417 mapper schema drift")
    if mapper.get("verdict") != "JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED":
        raise ValueError("1417 did not authorize CTX3 PatternEval targets")
    if not mapper.get("screen_passed") or not all((mapper.get("guards") or {}).values()):
        raise ValueError("1417 mapper guards are not all green")
    if _sha256(prediction_path) != (mapper.get("outputs") or {}).get("aligned_prediction_sha256"):
        raise ValueError("1417 aligned mapper prediction hash drift")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    if meta_schema != "JSM2":
        raise ValueError("CTX3 paired targets require JSM2")
    source = mapper.get("source") or {}
    if source.get("data_sha256") != _sha256(data_path) or source.get("meta_sha256") != _sha256(meta_path):
        raise ValueError("immutable 1417 data/meta hashes drift")
    prediction = np.load(prediction_path, mmap_mode="r", allow_pickle=False)
    if prediction.shape != (len(records),) or prediction.dtype != np.float32:
        raise ValueError("1417 aligned mapper prediction shape/dtype drift")
    train_count = int(args.train_count)
    if train_count != int(source.get("train_records", -1)):
        raise ValueError("1417 train_count drift")
    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    opening_ids = np.asarray(metadata["opening_id"], dtype=np.uint64)
    folds = game_folds(opening_ids, 5, int(args.fold_seed))
    tempo = tempo_phase_from_records(records)
    phase_bins = np.minimum(np.floor(tempo * 4).astype(np.int16), 3)
    wdl_codes = np.asarray(outcomes + 1.0, dtype=np.int16)
    strata = wdl_codes * 4 + phase_bins
    aligned, shuffled, shuffle_report = compose_targets(
        prediction,
        outcomes,
        folds,
        strata,
        train_count,
        alpha=float(args.alpha),
        shuffle_seed=int(args.shuffle_seed),
    )
    _atomic_save_npy(aligned_path, aligned)
    _atomic_save_npy(shuffled_path, shuffled)
    payload = {
        "schema": "jass.l3_context3_paired_targets.v1",
        "verdict": "JASS_CONTEXT3_PAIRED_TARGETS_READY",
        "records": int(len(records)),
        "train_records": train_count,
        "holdout_records": int(len(records) - train_count),
        "selected_candidate": mapper["protocol"]["selected_candidate"],
        "target": {
            "formula": "(1-alpha)*terminal_wdl_black+alpha*ctx3_tanh_wdl_black",
            "alpha": float(args.alpha),
            "output_pov": "black",
            "output_range": "win_probability_[0,1]",
        },
        "mapping": {
            "source_mapper": "1417_exact_tanh_aligned",
            "fold_group": "opening_id",
            "fold_count": 5,
            "fold_seed": int(args.fold_seed),
            "train_predictions": "out_of_fold",
            "holdout_predictions": "final_train_fit",
        },
        "shuffle_control": {
            **shuffle_report,
            "phase_bin_count": 4,
            "wdl_stratified": True,
        },
        "source": {
            "data_sha256": _sha256(data_path),
            "meta_sha256": _sha256(meta_path),
            "mapper_report_sha256": _sha256(mapper_report_path),
            "aligned_prediction_sha256": _sha256(prediction_path),
        },
        "outputs": {
            "aligned_sha256": _sha256(aligned_path),
            "shuffled_sha256": _sha256(shuffled_path),
        },
        "frozen_read": False,
        "promotion_authorized": False,
    }
    _atomic_write_json(report_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--prediction", required=True)
    parser.add_argument("--mapper-report", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--aligned-out", required=True)
    parser.add_argument("--shuffled-out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--alpha", type=float, default=0.30)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=2026081906)
    args = parser.parse_args(argv)
    print(json.dumps(run(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
