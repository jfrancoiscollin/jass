from __future__ import annotations

import numpy as np

from mini_jass_lab.split import build_split


def test_split_is_deterministic_and_has_no_canonical_leakage(synthetic_oracle) -> None:
    first = build_split(synthetic_oracle, seed=17)
    second = build_split(synthetic_oracle, seed=17)
    assert first.manifest == second.manifest
    assert np.array_equal(first.canonical_assignments, second.canonical_assignments)
    for canonical_id in range(30):
        raw = np.flatnonzero(synthetic_oracle.canonical_ids == canonical_id)
        assert np.unique(first.raw_assignments[raw]).size == 1


def test_split_is_exactly_stratified_for_fixture(synthetic_oracle) -> None:
    split = build_split(synthetic_oracle, seed=17)
    assert split.manifest["canonical_counts"] == {
        "train": 21,
        "development": 3,
        "frozen_test": 6,
    }
    assert split.manifest["raw_counts"] == {
        "train": 42,
        "development": 6,
        "frozen_test": 12,
    }
    changed = build_split(synthetic_oracle, seed=18)
    assert changed.manifest["assignment_hash"] != split.manifest["assignment_hash"]
