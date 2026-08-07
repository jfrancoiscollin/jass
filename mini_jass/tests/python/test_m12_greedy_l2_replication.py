from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mini_jass_lab.greedy_l2_replication import (
    FRESH_PAIRED_SEEDS,
    build_greedy_l2_replication_recommendation,
    derive_greedy_replication_split,
    resolve_greedy_l2_replication_config,
)
from mini_jass_lab.split import SplitDefinition


def test_m12_split_is_deterministic_train_derived_and_excludes_m11() -> None:
    canonical_count = 30
    oracle = SimpleNamespace(
        manifest={"canonical_state_count": canonical_count, "solver_hash": 42},
        state_count=canonical_count,
        canonical_ids=np.arange(canonical_count, dtype=np.uint32),
        canonical_transforms=np.zeros(canonical_count, dtype=np.bool_),
        bitboards=np.tile(np.asarray([[1, 2, 0, 0]], dtype=np.uint16), (canonical_count, 1)),
        values=(np.arange(canonical_count) % 3 - 1).astype(np.int8),
    )
    assignments = np.asarray([0] * 24 + [1] * 3 + [2] * 3, dtype=np.uint8)
    historical = SplitDefinition(
        assignments,
        assignments.copy(),
        {"manifest_hash": "historical-split"},
    )
    excluded = np.asarray([1, 5, 9, 13], dtype=np.int64)
    first = derive_greedy_replication_split(
        oracle, historical, excluded, 20260809
    )
    second = derive_greedy_replication_split(
        oracle, historical, excluded, 20260809
    )
    assert first.manifest == second.manifest
    assert np.array_equal(first.canonical_assignments, second.canonical_assignments)
    assert np.all(first.canonical_assignments[excluded] == 3)
    selected = np.concatenate(
        [first.indices(cohort) for cohort in ("train", "development", "confirmation")]
    )
    assert np.all(historical.raw_assignments[selected] == 0)
    assert not set(selected).intersection(set(excluded))
    assert first.manifest["source_cohort"] == (
        "historical_train_after_m11_exclusion"
    )


def test_m12_config_freezes_fresh_seeds_greedy_and_m9_thresholds() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = resolve_greedy_l2_replication_config(
        root / "configs/l2_greedy_replication.yaml"
    )
    assert tuple(resolved["paired_seeds"]) == FRESH_PAIRED_SEEDS
    assert resolved["mechanism_overrides"] == {
        "self_play.exploration.strategy": "greedy"
    }
    assert resolved["replication_split"] == {
        "seed": 20260809,
        "train_fraction": 0.70,
        "development_fraction": 0.15,
        "confirmation_fraction": 0.15,
    }
    assert resolved["scientific_gate"] == {
        "minimum_mean_value_sign_delta": 0.0,
        "minimum_mean_optimal_mass_delta": 0.0,
        "minimum_target_value_exact_rate": 0.70,
        "minimum_target_optimal_mass": 0.85,
    }


def test_m12_gate_can_authorize_preparation_but_never_production_transfer() -> None:
    aggregate = {
        "successful_run_count": 5,
        "deterministic_replay": True,
        "greedy_behavior_only": True,
        "training_sample_filter_enforced": True,
        "historical_train_only": True,
        "m11_holdout_evaluation_reads": 0,
        "historical_nontrain_evaluation_reads": 0,
        "mean_development_value_sign_delta": 0.03,
        "mean_development_optimal_mass_delta": 0.02,
        "development_selection_score_confidence_95": [0.01, 0.09],
        "mean_confirmation_value_sign_delta": 0.02,
        "mean_confirmation_optimal_mass_delta": 0.01,
        "confirmation_selection_score_confidence_95": [0.005, 0.06],
        "mean_target_value_exact_rate": 0.76,
        "mean_target_optimal_mass": 0.90,
        "eligible_candidate_count": 1,
    }
    thresholds = {
        "minimum_mean_value_sign_delta": 0.0,
        "minimum_mean_optimal_mass_delta": 0.0,
        "minimum_target_value_exact_rate": 0.70,
        "minimum_target_optimal_mass": 0.85,
    }
    recommendation = build_greedy_l2_replication_recommendation(
        aggregate, thresholds
    )
    assert recommendation["gate"]["status"] == "PASS"
    assert recommendation["l2_replication_confirmed"] is True
    assert recommendation["implementation_preparation_authorized"] is True
    assert recommendation["production_jass_changes_authorized"] is False
    assert recommendation["direct_10x10_transfer_authorized"] is False
