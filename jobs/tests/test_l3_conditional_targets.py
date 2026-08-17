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


def _write_ctx2_fixture(tmp_path: Path) -> tuple[Path, Path, Path, int]:
    openings_per_cohort = 30
    rows_per_opening = 4
    fold_seed = 81
    train_openings = np.arange(1_000, 1_000 + openings_per_cohort, dtype=np.uint64)
    holdout_openings = np.arange(2_000, 2_000 + openings_per_cohort, dtype=np.uint64)
    all_openings = np.concatenate((train_openings, holdout_openings))
    count = len(all_openings) * rows_per_opening
    train_count = len(train_openings) * rows_per_opening
    records = np.zeros(count, dtype=TARGETS.JNNW_DTYPE)
    meta = np.zeros(count, dtype=TARGETS.JSM2_DTYPE)
    features = np.zeros((count, 30), dtype=np.float32)
    outcomes_by_opening: dict[int, int] = {}
    for cohort in (train_openings, holdout_openings):
        fold_ids = TARGETS.game_folds(cohort, 2, fold_seed)
        for fold in range(2):
            members = cohort[fold_ids == fold]
            assert len(members) >= 3
            for rank, opening in enumerate(members):
                outcomes_by_opening[int(opening)] = (-1, 0, 1)[rank % 3]
    row = 0
    game = 10_000
    for opening in all_openings:
        outcome = outcomes_by_opening[int(opening)]
        for local in range(rows_per_opening):
            records["stm"][row] = 1
            records["wdl"][row] = outcome
            meta["game_id"][row] = game + local // 2
            meta["opening_id"][row] = opening
            meta["ply"][row] = local
            meta["game_plies"][row] = 2
            meta["game_result"][row] = outcome
            # Empty bitboards have tempo phase zero, hence the useful signal
            # sits in the end bank (offset 15). Small within-game variation
            # prevents accidental duplicate-row shortcuts.
            features[row, 15] = outcome * (2.0 + 0.1 * local)
            features[row, 16] = outcome * (1.0 + 0.05 * local)
            row += 1
        game += 2
    data = tmp_path / "ctx2.jnnw"
    sidecar = tmp_path / "ctx2.jsm"
    feat = tmp_path / "ctx2.feat"
    data.write_bytes(b"JNNW" + struct.pack("<I", count) + records.tobytes())
    sidecar.write_bytes(b"JSM2" + struct.pack("<I", count) + meta.tobytes())
    feat.write_bytes(b"FEAT" + struct.pack("<II", count, 30) + features.tobytes())
    return data, sidecar, feat, train_count


def test_ctx1_legacy_matrix_reproduces_historical_paired_layout() -> None:
    features = np.zeros((2, 120), dtype=np.float32)
    features[0, 100] = 3
    features[0, 101] = 1
    features[0, 0] = 1
    features[0, 50:52] = 1
    features[0, 110] = 7
    features[0, 111] = 2
    features[1] = features[0]
    # Reproduce the historical pair-swap contract exactly.  This is not a
    # physical board-symmetry test: CTX1's signed balance pair is one reason the
    # new CTX2 schema replaces it instead of silently changing old artefacts.
    features[1, :50] = features[0, 50:100]
    features[1, 50:100] = features[0, :50]
    for left in (100, 102, 104, 106, 108, 110, 112, 114, 116, 118):
        features[1, left] = features[0, left + 1]
        features[1, left + 1] = features[0, left]
    context = TARGETS.context_matrix(features)
    np.testing.assert_array_equal(context[1], -context[0])
    with pytest.raises(ValueError, match="120-extra"):
        TARGETS.context_matrix(np.zeros((2, 119), dtype=np.float32))


def test_ctx2_context_is_explicitly_30_wide_and_phase_split() -> None:
    features = np.arange(60, dtype=np.float32).reshape(2, 30)
    context = TARGETS.context_matrix(features, "ctx2-phase-tactical-30")
    np.testing.assert_array_equal(context, features.astype(np.float64))
    assert len(TARGETS.CTX2_BASE_COMPONENTS) == 15
    assert len(TARGETS.CTX2_CONTEXT_COMPONENTS) == 30
    assert TARGETS.CTX2_CONTEXT_COMPONENTS[0].startswith("tempo_mid_")
    assert TARGETS.CTX2_CONTEXT_COMPONENTS[15].startswith("tempo_end_")
    with pytest.raises(ValueError, match="30-wide"):
        TARGETS.context_matrix(np.zeros((2, 29)), "ctx2-phase-tactical-30")


def test_game_equal_weights_remove_trajectory_length_bias() -> None:
    games = np.asarray([1, 2, 2, 3, 3, 3], dtype=np.uint64)
    weights = TARGETS._game_equal_weights(games)
    totals = [float(weights[games == game].sum()) for game in (1, 2, 3)]
    np.testing.assert_allclose(totals, np.ones(3), atol=0.0, rtol=0.0)


def test_opening_folds_and_scalers_are_blind_to_holdout_features() -> None:
    train_count = 16
    count = 24
    games = np.arange(100, 100 + count, dtype=np.uint64)
    openings = np.repeat(np.arange(200, 200 + count // 2, dtype=np.uint64), 2)
    outcomes = np.where(np.arange(count) % 2 == 0, 1.0, -1.0)
    matrix = np.column_stack(
        (
            outcomes + np.linspace(-0.2, 0.2, count),
            np.linspace(-2.0, 3.0, count),
        )
    )
    altered = matrix.copy()
    altered[train_count:] *= 1_000_000.0
    common = dict(
        group_ids=openings,
        group_name="opening_id",
        row_weighting="game_equal",
        components=("signal", "drift"),
        fold_count=2,
        fold_seed=81,
        ridge=1e-4,
        max_iterations=50,
        tolerance=1e-8,
        line_search_steps=20,
    )
    predictions, folds, report = TARGETS.cross_fitted_predictions(
        matrix, outcomes, games, train_count, **common
    )
    altered_predictions, _, altered_report = TARGETS.cross_fitted_predictions(
        altered, outcomes, games, train_count, **common
    )
    np.testing.assert_allclose(
        predictions[:train_count], altered_predictions[:train_count], atol=0.0, rtol=0.0
    )
    assert report["train_rms_scale"] == altered_report["train_rms_scale"]
    assert report["fold_local_rms"] is True
    assert report["fold_group"] == "opening_id"
    assert report["each_game_total_weight_equal"] is True
    for opening in np.unique(openings):
        assert len(np.unique(folds[openings == opening])) == 1
    assert all(row["rms_fitted_on_training_rows_only"] for row in report["folds"])


def test_tempo_phase_matches_fmjd_start_geometry() -> None:
    records = np.zeros(2, dtype=TARGETS.JNNW_DTYPE)
    records["wm"] = sum(1 << bit for bit in range(30, 50))
    records["bm"] = sum(1 << bit for bit in range(0, 20))
    phase = TARGETS.tempo_phase_from_records(records, chunk_size=1)
    np.testing.assert_allclose(phase, np.ones(2), atol=0.0, rtol=0.0)


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


def test_ctx2_strict_protocol_runs_end_to_end(tmp_path: Path) -> None:
    data, meta, feat, train_count = _write_ctx2_fixture(tmp_path)
    args = argparse.Namespace(
        data=str(data),
        meta=str(meta),
        feat=str(feat),
        context_schema="ctx2-phase-tactical-30",
        group_by="opening_id",
        row_weighting="game_equal",
        require_convergence=True,
        train_count=train_count,
        aligned_out=str(tmp_path / "ctx2-aligned.npy"),
        shuffled_out=str(tmp_path / "ctx2-shuffled.npy"),
        report=str(tmp_path / "ctx2-report.json"),
        alpha=0.30,
        fold_count=2,
        fold_seed=81,
        shuffle_seed=82,
        shuffle_within_wdl=True,
        shuffle_phase_bins=4,
        ridge=1e-4,
        max_iterations=100,
        tolerance=1e-8,
        line_search_steps=20,
    )
    report = TARGETS.run(args)
    assert report["schema"] == "jass.l3_conditional_targets.v2"
    assert report["context_schema"] == "ctx2-phase-tactical-30"
    assert report["target"]["exact_legal_move_context"] is True
    assert report["mapping"]["fold_group"] == "opening_id"
    assert report["mapping"]["each_game_total_weight_equal"] is True
    assert report["mapping"]["fold_local_rms"] is True
    assert all(row["fit"]["converged"] for row in report["mapping"]["folds"])
    assert report["mapping"]["final_train_fit"]["fit"]["converged"] is True
    assert report["shuffle_control"]["stratification"] == (
        "terminal_wdl_black_x_tempo_phase_4_bins"
    )
    assert report["shuffle_control"]["all_final_target_marginals_preserved"] is True


def test_alpha_one_is_a_complete_conditional_relabel(tmp_path: Path) -> None:
    data, meta, feat, train_count = _write_ctx2_fixture(tmp_path)
    common = dict(
        data=str(data),
        meta=str(meta),
        feat=str(feat),
        context_schema="ctx2-phase-tactical-30",
        group_by="opening_id",
        row_weighting="game_equal",
        require_convergence=True,
        train_count=train_count,
        fold_count=2,
        fold_seed=81,
        shuffle_seed=82,
        shuffle_within_wdl=True,
        shuffle_phase_bins=4,
        ridge=1e-4,
        max_iterations=100,
        tolerance=1e-8,
        line_search_steps=20,
    )
    full_args = argparse.Namespace(
        **common,
        aligned_out=str(tmp_path / "full-aligned.npy"),
        shuffled_out=str(tmp_path / "full-shuffled.npy"),
        report=str(tmp_path / "full-report.json"),
        alpha=1.0,
    )
    mixed_args = argparse.Namespace(
        **common,
        aligned_out=str(tmp_path / "mixed-aligned.npy"),
        shuffled_out=str(tmp_path / "mixed-shuffled.npy"),
        report=str(tmp_path / "mixed-report.json"),
        alpha=0.5,
    )
    full = TARGETS.run(full_args)
    TARGETS.run(mixed_args)
    full_values = np.load(full_args.aligned_out, allow_pickle=False)
    mixed_values = np.load(mixed_args.aligned_out, allow_pickle=False)
    records = TARGETS._open_counted(data, b"JNNW", TARGETS.JNNW_DTYPE)
    black_wdl = np.where(records["stm"] == 1, records["wdl"], -records["wdl"])
    outcomes = (black_wdl + 1.0) * 0.5
    # At alpha=.5: mixed=.5*outcome+.5*prediction.  Therefore the alpha=1
    # target must recover prediction=2*mixed-outcome exactly up to float32.
    np.testing.assert_allclose(
        full_values,
        2.0 * mixed_values - outcomes,
        atol=2e-7,
        rtol=0.0,
    )
    assert full["target"]["alpha"] == 1.0


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
