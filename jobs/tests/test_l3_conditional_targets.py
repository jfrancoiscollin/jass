# SPDX-License-Identifier: AGPL-3.0-or-later
"""Causal and leakage contracts for full-Jass conditional targets."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import struct

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "l3_conditional_targets.py"
SPEC = importlib.util.spec_from_file_location("l3_conditional_targets", TOOL)
assert SPEC is not None and SPEC.loader is not None
TARGETS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TARGETS)


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, int]:
    rows_per_game = 3
    games = 12
    count = rows_per_game * games
    train_count = 8 * rows_per_game
    records = np.zeros(count, dtype=TARGETS.JNNW_DTYPE)
    meta = np.zeros(count, dtype=TARGETS.JSM1_DTYPE)
    features = np.zeros((count, 120), dtype=np.float32)
    for game in range(games):
        outcome = 1 if game % 2 == 0 else -1
        sl = slice(game * rows_per_game, (game + 1) * rows_per_game)
        records["stm"][sl] = 1
        records["wdl"][sl] = outcome
        meta["game_id"][sl] = game + 100
        meta["opening_id"][sl] = game + 1000
        # All components are inference-time FEAT values.  Men delta alone is
        # perfectly predictive; small ply variation prevents duplicate rows.
        if outcome > 0:
            features[sl, 100] = np.asarray([2.0, 3.0, 4.0])
        else:
            features[sl, 101] = np.asarray([2.0, 3.0, 4.0])

    data = tmp_path / "fixture.jnnw"
    sidecar = tmp_path / "fixture.jsm"
    feat = tmp_path / "fixture.feat"
    data.write_bytes(b"JNNW" + struct.pack("<I", count) + records.tobytes())
    sidecar.write_bytes(b"JSM1" + struct.pack("<I", count) + meta.tobytes())
    feat.write_bytes(
        b"FEAT" + struct.pack("<II", count, 120) + features.astype("<f4").tobytes()
    )
    return data, sidecar, feat, train_count


def test_context_matrix_uses_only_odd_paired_production_extras() -> None:
    features = np.zeros((2, 120), dtype=np.float32)
    features[0, 100] = 3
    features[0, 101] = 1
    features[0, 0] = 1
    features[0, 50:52] = 1
    features[0, 110] = 7
    features[0, 111] = 2
    features[1] = features[0]
    # Swap every black/white member of the fixed production layout.
    features[1, :50] = features[0, 50:100]
    features[1, 50:100] = features[0, :50]
    for left in (100, 102, 104, 106, 108, 110, 112, 114, 116, 118):
        features[1, left] = features[0, left + 1]
        features[1, left + 1] = features[0, left]
    context = TARGETS.context_matrix(features)
    np.testing.assert_array_equal(context[1], -context[0])
    with pytest.raises(ValueError, match="120-extra"):
        TARGETS.context_matrix(np.zeros((2, 119), dtype=np.float32))


def test_cross_fit_groups_complete_games_and_shuffle_preserves_marginals(
    tmp_path: Path,
) -> None:
    data, meta, feat, train_count = _write_fixture(tmp_path)
    args = argparse.Namespace(
        data=str(data),
        meta=str(meta),
        feat=str(feat),
        train_count=train_count,
        aligned_out=str(tmp_path / "aligned.npy"),
        shuffled_out=str(tmp_path / "shuffled.npy"),
        report=str(tmp_path / "report.json"),
        alpha=0.30,
        fold_count=2,
        fold_seed=81,
        shuffle_seed=82,
        ridge=1e-4,
        max_iterations=50,
        tolerance=1e-8,
        line_search_steps=20,
    )
    report = TARGETS.run(args)
    aligned = np.load(args.aligned_out, allow_pickle=False)
    shuffled = np.load(args.shuffled_out, allow_pickle=False)

    assert aligned.dtype == np.float32
    assert shuffled.dtype == np.float32
    assert aligned.shape == shuffled.shape == (36,)
    assert report["mapping"]["all_games_fold_disjoint"] is True
    assert report["mapping"]["train_holdout_game_overlap"] == 0
    assert report["mapping"]["oof_mse_gain_vs_state_blind"] > 0.0
    assert report["shuffle_control"]["fixed_point_count"] == 0
    assert report["shuffle_control"]["all_cohort_fold_marginals_preserved"] is True
    assert report["target"]["oracle_or_egdb_signal"] is False
    assert report["target"]["new_selfplay_generated"] is False
    assert np.all((0.0 <= aligned) & (aligned <= 1.0))
    assert np.all((0.0 <= shuffled) & (shuffled <= 1.0))
    assert not np.array_equal(aligned, shuffled)


def test_train_holdout_game_overlap_is_rejected() -> None:
    matrix = np.asarray([[1.0], [1.0], [-1.0], [-1.0]])
    outcomes = np.asarray([1.0, 1.0, -1.0, -1.0])
    games = np.asarray([1, 2, 1, 3], dtype=np.uint64)
    with pytest.raises(ValueError, match="complete games cross"):
        TARGETS.cross_fitted_predictions(
            matrix,
            outcomes,
            games,
            2,
            fold_count=2,
            fold_seed=1,
            ridge=1e-4,
            max_iterations=5,
            tolerance=1e-8,
            line_search_steps=5,
        )
