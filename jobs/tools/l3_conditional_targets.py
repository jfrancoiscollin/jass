#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build leakage-resistant conditional target sidecars for full-size Jass.

The mapper sees only dense FEAT components already available to PatternEval at
inference time.  Terminal WDL is converted to black POV.  Train rows receive
out-of-fold predictions grouped by complete JSM games; holdout rows receive a
prediction from a mapper fitted on the train prefix only.  The shuffled control
preserves each cohort/fold prediction multiset while breaking row alignment.
No oracle, EGDB label, search score, frozen cohort, or new self-play is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import time
from typing import Any

import numpy as np

JNNW_DTYPE = np.dtype(
    [
        ("wm", "<u8"),
        ("wk", "<u8"),
        ("bm", "<u8"),
        ("bk", "<u8"),
        ("stm", "u1"),
        ("score", "<i4"),
        ("wdl", "i1"),
    ]
)
JSM1_DTYPE = np.dtype(
    [("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1")]
)
JSM2_DTYPE = np.dtype(
    [
        ("game_id", "<u8"),
        ("opening_id", "<u8"),
        ("seeded", "u1"),
        ("ply", "<u2"),
        ("game_plies", "<u2"),
        ("last_eps_ply", "<u2"),
        ("game_result", "i1"),
        ("flags", "u1"),
    ]
)
assert JNNW_DTYPE.itemsize == 38
assert JSM1_DTYPE.itemsize == 17
assert JSM2_DTYPE.itemsize == 25

CONTEXT_COMPONENTS = (
    "men_delta",
    "king_count_delta",
    "mobility_delta",
    "balance_delta",
    "king_centrality_delta",
    "king_proximity_delta",
    "king_safe_mobility_delta",
    "king_denied_delta",
    "men_skew_delta",
    "has_king_delta",
    "extra_king_delta",
)
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_counted(path: Path, magic: bytes, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != magic:
        raise ValueError(f"{path}: expected {magic!r} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + count * dtype.itemsize
    if path.stat().st_size != expected:
        raise ValueError(f"{path}: size {path.stat().st_size} != {expected}")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(count,))


def _open_meta(path: Path, expected_count: int) -> tuple[np.memmap, str]:
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic == b"JSM1":
        rows = _open_counted(path, magic, JSM1_DTYPE)
    elif magic == b"JSM2":
        rows = _open_counted(path, magic, JSM2_DTYPE)
    else:
        raise ValueError(f"{path}: expected JSM1 or JSM2")
    if len(rows) != expected_count:
        raise ValueError(f"{path}: metadata rows {len(rows)} != data {expected_count}")
    return rows, magic.decode("ascii")


def _open_feat(path: Path, expected_count: int) -> tuple[np.memmap, int]:
    with path.open("rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT header")
    count, width = struct.unpack_from("<II", header, 4)
    if count != expected_count:
        raise ValueError(f"{path}: FEAT rows {count} != data {expected_count}")
    expected = 12 + count * width * 4
    if path.stat().st_size != expected:
        raise ValueError(f"{path}: FEAT size {path.stat().st_size} != {expected}")
    return (
        np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width)),
        int(width),
    )


def context_matrix(features: np.ndarray) -> np.ndarray:
    """Return odd, black-minus-white context from the production 120 extras."""
    raw = np.asarray(features)
    if raw.ndim != 2 or raw.shape[1] != 120:
        raise ValueError(
            f"conditional transfer requires the L2LOW 120-extra architecture, got {raw.shape}"
        )
    values = np.empty((raw.shape[0], len(CONTEXT_COMPONENTS)), dtype=np.float64)
    values[:, 0] = raw[:, 100] - raw[:, 101]
    values[:, 1] = raw[:, :50].sum(axis=1) - raw[:, 50:100].sum(axis=1)
    values[:, 2] = raw[:, 102] - raw[:, 103]
    values[:, 3] = raw[:, 104] - raw[:, 105]
    values[:, 4] = raw[:, 106] - raw[:, 107]
    values[:, 5] = raw[:, 108] - raw[:, 109]
    values[:, 6] = raw[:, 110] - raw[:, 111]
    values[:, 7] = raw[:, 112] - raw[:, 113]
    values[:, 8] = raw[:, 114] - raw[:, 115]
    values[:, 9] = raw[:, 116] - raw[:, 117]
    values[:, 10] = raw[:, 118] - raw[:, 119]
    if not np.all(np.isfinite(values)):
        raise ValueError("conditional context contains non-finite values")
    return values


def _splitmix64(values: np.ndarray) -> np.ndarray:
    with np.errstate(over="ignore"):
        z = np.asarray(values, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def game_folds(game_ids: np.ndarray, fold_count: int, seed: int) -> np.ndarray:
    if fold_count < 2:
        raise ValueError("fold_count must be >= 2")
    mixed = _splitmix64(np.asarray(game_ids, dtype=np.uint64) ^ np.uint64(seed))
    return np.asarray(mixed % np.uint64(fold_count), dtype=np.int8)


def _loss(matrix: np.ndarray, targets: np.ndarray, theta: np.ndarray, ridge: float) -> float:
    residual = np.tanh(matrix @ theta) - targets
    return 0.5 * float(np.mean(residual * residual)) + 0.5 * ridge * float(theta @ theta)


def fit_tanh_linear(
    matrix: np.ndarray,
    targets: np.ndarray,
    *,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    x = np.asarray(matrix, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    if x.ndim != 2 or y.shape != (x.shape[0],) or x.shape[0] == 0:
        raise ValueError("fit requires non-empty aligned matrix and targets")
    theta = np.zeros(x.shape[1], dtype=np.float64)
    identity = np.eye(x.shape[1], dtype=np.float64)
    current = _loss(x, y, theta, ridge)
    initial = current
    converged = False
    iterations = 0
    for iteration in range(max_iterations):
        prediction = np.tanh(x @ theta)
        derivative = 1.0 - prediction * prediction
        residual = prediction - y
        gradient = x.T @ (derivative * residual) / len(y) + ridge * theta
        weighted = x * derivative[:, None]
        hessian = weighted.T @ weighted / len(y) + (ridge + 1e-12) * identity
        step = np.linalg.solve(hessian, gradient)
        accepted = False
        scale = 1.0
        candidate = theta
        candidate_loss = current
        for _ in range(line_search_steps):
            proposal = theta - scale * step
            proposal_loss = _loss(x, y, proposal, ridge)
            if proposal_loss < current:
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
        current = candidate_loss
        if update <= tolerance:
            converged = True
            break
    if not np.all(np.isfinite(theta)):
        raise RuntimeError("conditional fit produced non-finite coefficients")
    return theta, {
        "row_count": int(len(y)),
        "initial_loss": initial,
        "final_loss": current,
        "iterations": iterations,
        "converged": converged,
    }


def cross_fitted_predictions(
    matrix: np.ndarray,
    outcomes: np.ndarray,
    game_ids: np.ndarray,
    train_count: int,
    *,
    fold_count: int,
    fold_seed: int,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    n = len(outcomes)
    if matrix.shape[0] != n or game_ids.shape != (n,):
        raise ValueError("conditional arrays are not aligned")
    if not 0 < train_count < n:
        raise ValueError("train_count must leave non-empty train and holdout cohorts")
    train_games = set(int(value) for value in np.unique(game_ids[:train_count]))
    holdout_games = set(int(value) for value in np.unique(game_ids[train_count:]))
    overlap = train_games & holdout_games
    if overlap:
        raise ValueError(f"{len(overlap)} complete games cross train/holdout boundary")

    train_raw = matrix[:train_count]
    rms = np.sqrt(np.mean(train_raw * train_raw, axis=0))
    rms = np.where(rms > 1e-12, rms, 1.0)
    scaled = matrix / rms
    folds = game_folds(game_ids, fold_count, fold_seed)
    predictions = np.empty(n, dtype=np.float64)
    blind = np.empty(train_count, dtype=np.float64)
    fold_rows: list[dict[str, Any]] = []
    train_positions = np.arange(train_count, dtype=np.int64)
    for fold in range(fold_count):
        evaluation = train_positions[folds[:train_count] == fold]
        training = train_positions[folds[:train_count] != fold]
        if evaluation.size == 0 or training.size == 0:
            raise ValueError(f"conditional fold {fold} is empty")
        training_games = set(int(value) for value in np.unique(game_ids[training]))
        evaluation_games = set(int(value) for value in np.unique(game_ids[evaluation]))
        if training_games & evaluation_games:
            raise RuntimeError("a complete game crossed an OOF fold")
        theta, fit = fit_tanh_linear(
            scaled[training],
            outcomes[training],
            ridge=ridge,
            max_iterations=max_iterations,
            tolerance=tolerance,
            line_search_steps=line_search_steps,
        )
        predictions[evaluation] = np.tanh(scaled[evaluation] @ theta)
        blind[evaluation] = float(np.mean(outcomes[training]))
        fold_rows.append(
            {
                "fold": fold,
                "training_rows": int(training.size),
                "evaluation_rows": int(evaluation.size),
                "training_games": len(training_games),
                "evaluation_games": len(evaluation_games),
                "game_disjoint": True,
                "theta_scaled": [float(value) for value in theta],
                "fit": fit,
            }
        )

    final_theta, final_fit = fit_tanh_linear(
        scaled[:train_count],
        outcomes[:train_count],
        ridge=ridge,
        max_iterations=max_iterations,
        tolerance=tolerance,
        line_search_steps=line_search_steps,
    )
    predictions[train_count:] = np.tanh(scaled[train_count:] @ final_theta)
    if not np.all(np.isfinite(predictions)) or np.any(np.abs(predictions) > 1.0):
        raise RuntimeError("conditional predictions left finite WDL range")
    oof_mse = float(np.mean((predictions[:train_count] - outcomes[:train_count]) ** 2))
    blind_mse = float(np.mean((blind - outcomes[:train_count]) ** 2))
    return predictions, folds, {
        "components": list(CONTEXT_COMPONENTS),
        "train_rms_scale": [float(value) for value in rms],
        "scale_is_positive_only_no_mean_centering": True,
        "fold_count": fold_count,
        "fold_seed": fold_seed,
        "folds": fold_rows,
        "all_games_fold_disjoint": True,
        "train_holdout_game_overlap": 0,
        "train_unique_games": len(train_games),
        "holdout_unique_games": len(holdout_games),
        "oof_mse_vs_wdl": oof_mse,
        "state_blind_oof_mse_vs_wdl": blind_mse,
        "oof_mse_gain_vs_state_blind": blind_mse - oof_mse,
        "final_train_fit": {
            "theta_scaled": [float(value) for value in final_theta],
            "theta_raw": [float(value) for value in final_theta / rms],
            "fit": final_fit,
        },
    }


def shuffled_within_cohort_folds(
    predictions: np.ndarray,
    folds: np.ndarray,
    train_count: int,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    values = np.asarray(predictions, dtype=np.float64)
    shuffled = np.empty_like(values)
    sources = np.empty(len(values), dtype=np.int64)
    row_ids = np.arange(len(values), dtype=np.uint64)
    for start, stop, cohort in (
        (0, train_count, "train"),
        (train_count, len(values), "holdout"),
    ):
        for fold in sorted(int(value) for value in np.unique(folds[start:stop])):
            members = np.flatnonzero(folds[start:stop] == fold) + start
            if members.size < 2:
                raise ValueError(f"{cohort} fold {fold} has fewer than two rows")
            keys = _splitmix64(row_ids[members] ^ np.uint64(seed) ^ np.uint64(fold))
            ordered = members[np.argsort(keys, kind="stable")]
            rotated = np.roll(ordered, 1)
            shuffled[ordered] = values[rotated]
            sources[ordered] = rotated
            if not np.array_equal(np.sort(shuffled[ordered]), np.sort(values[ordered])):
                raise RuntimeError("shuffle changed a cohort/fold marginal")
    if np.any(sources == np.arange(len(values), dtype=np.int64)):
        raise RuntimeError("shuffle retained a source row")
    if np.any((sources < train_count) != (np.arange(len(values)) < train_count)):
        raise RuntimeError("shuffle crossed train/holdout cohorts")
    if not np.array_equal(folds[sources], folds):
        raise RuntimeError("shuffle crossed conditional folds")
    return shuffled, {
        "seed": seed,
        "fixed_point_count": 0,
        "all_sources_within_same_cohort": True,
        "all_sources_within_same_fold": True,
        "all_cohort_fold_marginals_preserved": True,
        "permutation_hash": hashlib.sha256(sources.tobytes(order="C")).hexdigest(),
    }


def _atomic_save_npy(path: Path, values: np.ndarray) -> None:
    if path.exists():
        raise ValueError(f"{path}: output exists (no-clobber)")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("xb") as handle:
            np.save(handle, values, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"{path}: output exists (no-clobber)") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"{path}: output exists (no-clobber)")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"{path}: output exists (no-clobber)") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    feat_path = Path(args.feat)
    aligned_path = Path(args.aligned_out)
    shuffled_path = Path(args.shuffled_out)
    report_path = Path(args.report)
    outputs = {path.resolve(strict=False) for path in (aligned_path, shuffled_path, report_path)}
    inputs = {path.resolve(strict=False) for path in (data_path, meta_path, feat_path)}
    if len(outputs) != 3 or outputs & inputs:
        raise ValueError("outputs must be distinct and cannot alias inputs")
    if any(path.exists() for path in (aligned_path, shuffled_path, report_path)):
        raise ValueError("conditional target outputs are no-clobber")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    train_count = int(args.train_count)
    if not 0 < train_count < len(records):
        raise ValueError("--train-count must leave non-empty train and holdout cohorts")
    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    if not np.all(np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("JNNW contains WDL outside {-1,0,1}")
    contexts = context_matrix(features)
    game_ids = np.asarray(metadata["game_id"], dtype=np.uint64)
    predictions, folds, mapping = cross_fitted_predictions(
        contexts,
        outcomes,
        game_ids,
        train_count,
        fold_count=int(args.fold_count),
        fold_seed=int(args.fold_seed),
        ridge=float(args.ridge),
        max_iterations=int(args.max_iterations),
        tolerance=float(args.tolerance),
        line_search_steps=int(args.line_search_steps),
    )
    shuffled, shuffle_report = shuffled_within_cohort_folds(
        predictions, folds, train_count, int(args.shuffle_seed)
    )
    alpha = float(args.alpha)
    if not 0.0 < alpha < 1.0:
        raise ValueError("--alpha must be strictly between 0 and 1")
    aligned_wdl = (1.0 - alpha) * outcomes + alpha * predictions
    shuffled_wdl = (1.0 - alpha) * outcomes + alpha * shuffled
    aligned = np.asarray((aligned_wdl + 1.0) * 0.5, dtype=np.float32)
    shuffled_targets = np.asarray((shuffled_wdl + 1.0) * 0.5, dtype=np.float32)
    if not (
        np.all(np.isfinite(aligned))
        and np.all(np.isfinite(shuffled_targets))
        and np.all((0.0 <= aligned) & (aligned <= 1.0))
        and np.all((0.0 <= shuffled_targets) & (shuffled_targets <= 1.0))
    ):
        raise RuntimeError("blended target left black-POV probability range")
    _atomic_save_npy(aligned_path, aligned)
    _atomic_save_npy(shuffled_path, shuffled_targets)
    report = {
        "schema": "jass.l3_conditional_targets.v1",
        "operation": "offline_conditional_target_transfer",
        "records": int(len(records)),
        "train_records": train_count,
        "holdout_records": int(len(records) - train_count),
        "meta_schema": meta_schema,
        "feature_width": width,
        "target": {
            "formula": "(1-alpha)*terminal_wdl_black+alpha*conditional_wdl_black",
            "alpha": alpha,
            "output_pov": "black",
            "output_range": "win_probability_[0,1]",
            "oracle_or_egdb_signal": False,
            "new_selfplay_generated": False,
        },
        "mapping": mapping,
        "shuffle_control": shuffle_report,
        "source": {
            "data": str(data_path),
            "data_sha256": _sha256(data_path),
            "meta": str(meta_path),
            "meta_sha256": _sha256(meta_path),
            "feat": str(feat_path),
            "feat_sha256": _sha256(feat_path),
        },
        "outputs": {
            "aligned": str(aligned_path),
            "aligned_sha256": _sha256(aligned_path),
            "shuffled": str(shuffled_path),
            "shuffled_sha256": _sha256(shuffled_path),
        },
        "elapsed_seconds": time.monotonic() - started,
    }
    _atomic_write_json(report_path, report)
    replayed = json.loads(report_path.read_text(encoding="utf-8"))
    if replayed.get("schema") != report["schema"] or replayed["outputs"] != report["outputs"]:
        raise RuntimeError("conditional target report round-trip failed")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="aligned JNNW corpus")
    parser.add_argument("--meta", required=True, help="aligned JSM1/JSM2 sidecar")
    parser.add_argument("--feat", required=True, help="aligned 120-wide FEAT dump")
    parser.add_argument("--train-count", required=True, type=int)
    parser.add_argument("--aligned-out", required=True, help="aligned float32 .npy")
    parser.add_argument("--shuffled-out", required=True, help="shuffled float32 .npy")
    parser.add_argument("--report", required=True)
    parser.add_argument("--alpha", type=float, default=0.30)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=20260812)
    parser.add_argument("--ridge", type=float, default=1e-4)
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--line-search-steps", type=int, default=20)
    args = parser.parse_args(argv)
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
