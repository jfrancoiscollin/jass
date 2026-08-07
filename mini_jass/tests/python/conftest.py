from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from mini_jass_lab.oracle import (  # noqa: E402
    EXPECTED_MANIFEST_HASH,
    EXPECTED_SOLVER_HASH,
    OracleArrays,
)


@pytest.fixture
def synthetic_oracle() -> OracleArrays:
    canonical_count = 30
    count = canonical_count * 2
    canonical_ids = np.repeat(np.arange(canonical_count, dtype=np.uint32), 2)
    values_by_class = (np.arange(canonical_count) % 3 - 1).astype(np.int8)
    values = values_by_class[canonical_ids]
    bitboards = np.zeros((count, 4), dtype=np.uint16)
    bitboards[:, 0] = 1 << 6
    bitboards[:, 1] = 1 << 7
    legal = np.zeros((count, 72), dtype=np.bool_)
    optimal = np.zeros((count, 72), dtype=np.bool_)
    children = np.full((count, 72), -1, dtype=np.int32)
    for index in range(count):
        action = index % 72
        legal[index, action] = True
        optimal[index, action] = True
        children[index, action] = (index + 1) % count
    return OracleArrays(
        manifest={
            "type": "manifest",
            "schema": "mini_jass.oracle_dataset.v1",
            "solver_hash": EXPECTED_SOLVER_HASH,
            "manifest_hash": EXPECTED_MANIFEST_HASH,
            "state_count": count,
            "canonical_state_count": canonical_count,
        },
        state_keys=np.arange(count, dtype=np.uint64),
        bitboards=bitboards,
        sides=(np.arange(count) % 2).astype(np.uint8),
        reversible_plies=(np.arange(count) % 21).astype(np.uint8),
        canonical_ids=canonical_ids,
        canonical_transforms=(np.arange(count) % 2 == 1),
        canonical_parent_counts=np.full(count, 2, dtype=np.uint8),
        values=values,
        dtw=np.where(values == 0, -1, 3).astype(np.int16),
        legal_mask=legal,
        optimal_mask=optimal,
        action_children=children,
    )
