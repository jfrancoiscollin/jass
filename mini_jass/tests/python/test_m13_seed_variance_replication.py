from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mini_jass_lab.seed_variance_replication import (
    EXPECTED_HOST,
    FRESH_POWERED_SEEDS,
    build_seed_variance_recommendation,
    derive_seed_variance_split,
    resolve_seed_variance_replication_config,
)


def test_m13_split_is_deterministic_and_nested_inside_m12_train() -> None:
    canonical_count = 36
    oracle = SimpleNamespace(
        manifest={"canonical_state_count": canonical_count, "solver_hash": 42},
        state_count=canonical_count,
        canonical_ids=np.arange(canonical_count, dtype=np.uint32),
        canonical_transforms=np.zeros(canonical_count, dtype=np.bool_),
        bitboards=np.tile(
            np.asarray([[1, 2, 0, 0]], dtype=np.uint16),
            (canonical_count, 1),
        ),
        values=(np.arange(canonical_count) % 3 - 1).astype(np.int8),
    )
    m12 = np.asarray(
        [0] * 24 + [1] * 3 + [2] * 3 + [3] * 3 + [4] * 3,
        dtype=np.uint8,
    )
    first = derive_seed_variance_split(
        oracle, m12, "m12-split", 20260810
    )
    second = derive_seed_variance_split(
        oracle, m12, "m12-split", 20260810
    )
    assert first.manifest == second.manifest
    assert np.array_equal(first.canonical_assignments, second.canonical_assignments)
    selected = np.concatenate(
        [first.indices(cohort) for cohort in ("train", "development", "confirmation")]
    )
    assert np.all(m12[selected] == 0)
    assert np.all(first.canonical_assignments[m12 == 1] == 3)
    assert np.all(first.canonical_assignments[m12 == 2] == 4)
    assert np.all(first.canonical_assignments[m12 == 3] == 5)
    assert np.all(first.canonical_assignments[m12 == 4] == 6)
    assert first.manifest["source_cohort"] == "m12_train_only"
    assert first.manifest["source_m12_split_manifest_hash"] == "m12-split"


def test_m13_config_freezes_power_fresh_data_cpx_and_unchanged_thresholds() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = resolve_seed_variance_replication_config(
        root / "configs/l2_seed_variance_replication.yaml"
    )
    assert tuple(resolved["paired_seeds"]) == FRESH_POWERED_SEEDS
    assert len(resolved["paired_seeds"]) == 20
    assert resolved["expected_execution_host"] == EXPECTED_HOST
    assert resolved["primary_inference"] == (
        "independent_m13_only_no_pooling_with_m12"
    )
    assert resolved["nested_split"] == {
        "seed": 20260810,
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
    assert resolved["power_analysis"]["anticipated_power"] >= 0.80
    assert resolved["power_analysis"]["fixed_replication_seed_count"] == 20


def test_m13_cpx_job_uses_cpu_torch_without_mutating_production_jass() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "jobs/run_m13_seed_variance_cpx.sh").read_text(
        encoding="utf-8"
    )
    assert "https://download.pytorch.org/whl/cpu" in script
    assert "torch==2.13.0" in script
    assert "pip install -r" not in script
    assert 'cmake -S "$repo/mini_jass"' in script
    assert "jass_production" not in script.lower()


def test_m13_gate_can_prepare_isolated_contract_but_never_modify_jass() -> None:
    aggregate = {
        "successful_run_count": 20,
        "deterministic_replay": True,
        "execution_host": EXPECTED_HOST,
        "m12_results_pooled_for_primary_inference": False,
        "greedy_behavior_only": True,
        "training_sample_filter_enforced": True,
        "m12_train_source_only": True,
        "m12_development_evaluation_reads": 0,
        "m12_confirmation_evaluation_reads": 0,
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
    recommendation = build_seed_variance_recommendation(aggregate, thresholds)
    assert recommendation["gate"]["status"] == "PASS"
    assert recommendation["seed_variance_resolved"] is True
    assert recommendation["implementation_preparation_authorized"] is True
    assert recommendation["production_jass_changes_authorized"] is False
    assert recommendation["direct_10x10_transfer_authorized"] is False
