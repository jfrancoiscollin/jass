# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS, JSM2_DTYPE
from jobs.tools.l3_context2_intervention_contribution_autopsy import (
    GENERATOR_CELLS,
    _concentration,
    _opening_is_holdout,
    analyse,
    recover_split_cell_ids,
)


def profile(shares: list[float], *, weight: float = 10.0, records: int = 100) -> dict:
    values = np.asarray(shares, dtype=np.float64)
    values /= values.sum()
    return {
        "source_records": records,
        "train_oof_rows": records * 9 // 10,
        "effective_game_equal_weight_sum": weight,
        "game_equal_weight_per_source_record": weight / records,
        "base_components": [
            {
                "component": name,
                "mean_absolute_logit_contribution": float(values[index]),
                "absolute_logit_share": float(values[index]),
                "mean_absolute_alpha_target_probability_effect": float(values[index]),
                "absolute_alpha_target_probability_effect_share": float(values[index]),
                "dominant_position_rate": float(index == int(np.argmax(values))),
            }
            for index, name in enumerate(CTX2_BASE_COMPONENTS)
        ],
        "base_15_concentration": _concentration(values),
    }


def audit(concentration: dict[str, float]) -> dict:
    return {
        "schema": "jass.l3_context2_fixed_contribution_audit.v1",
        "verdict": "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY",
        "cohorts": {"train_oof": {"base_15_concentration": concentration}},
    }


def corpus_summary(records: int = 100) -> dict:
    return {
        "schema": "jass.l3_context2_intervention_corpus.v1",
        "cell_quotas": {name: records for name in GENERATOR_CELLS},
        "cells": {
            name: {
                "wdl_stm_rates": {"-1": 0.4, "0": 0.2, "1": 0.4}
            }
            for name in GENERATOR_CELLS
        },
    }


def overall(cell_profiles: dict[str, dict]) -> dict:
    values = np.zeros(len(CTX2_BASE_COMPONENTS))
    for row in cell_profiles.values():
        weight = float(row["effective_game_equal_weight_sum"])
        values += weight * np.asarray(
            [item["mean_absolute_logit_contribution"] for item in row["base_components"]]
        )
    return {"base_15_concentration": _concentration(values)}


class ContributionAutopsyTests(unittest.TestCase):
    def test_quota_lattice_finds_rescue_when_cells_span_components(self) -> None:
        cells = {}
        for index, name in enumerate(GENERATOR_CELLS):
            shares = np.full(len(CTX2_BASE_COMPONENTS), 1e-4)
            shares[index] = 1.0
            cells[name] = profile(shares.tolist())
        reproduced = overall(cells)
        result = analyse(
            cell_profiles=cells,
            reproduced_overall=reproduced,
            intervention_audit=audit(reproduced["base_15_concentration"]),
            current_audit=audit({
                "largest_share": 0.30,
                "top3_share": 0.60,
                "effective_component_count": 4.0,
            }),
            corpus_summary=corpus_summary(),
        )
        lattice = result["fixed_mapper_quota_lattice"]
        self.assertTrue(lattice["quota_only_rescue_predicted"])
        self.assertGreater(lattice["full_gate_candidates"], 0)
        self.assertEqual(
            result["mechanism"]["diagnosis"],
            "quota_only_rescue_exists_under_fixed_mapper",
        )

    def test_quota_lattice_closes_identical_concentrated_cells(self) -> None:
        shares = [0.60, 0.20, 0.10] + [0.10 / 12.0] * 12
        cells = {name: profile(shares) for name in GENERATOR_CELLS}
        reproduced = overall(cells)
        result = analyse(
            cell_profiles=cells,
            reproduced_overall=reproduced,
            intervention_audit=audit(reproduced["base_15_concentration"]),
            current_audit=audit({
                "largest_share": 0.50,
                "top3_share": 0.85,
                "effective_component_count": 3.0,
            }),
            corpus_summary=corpus_summary(),
        )
        lattice = result["fixed_mapper_quota_lattice"]
        self.assertFalse(lattice["quota_only_rescue_predicted"])
        self.assertEqual(lattice["full_gate_candidates"], 0)
        self.assertIn("do_not_span", result["mechanism"]["diagnosis"])

    def test_source_cell_ids_follow_exact_split_order(self) -> None:
        quotas = {name: 2 for name in GENERATOR_CELLS}
        rows = np.zeros(sum(quotas.values()), dtype=JSM2_DTYPE)
        rows["game_id"] = np.arange(100, 100 + len(rows), dtype=np.uint64)
        rows["opening_id"] = np.arange(200, 200 + len(rows), dtype=np.uint64)
        rows["game_plies"] = 20
        seed = 577215
        hold = np.asarray(
            [_opening_is_holdout(int(value), seed, 10) for value in rows["opening_id"]]
        )
        order = np.concatenate((np.flatnonzero(~hold), np.flatnonzero(hold)))
        expected = np.repeat(np.arange(len(GENERATOR_CELLS), dtype=np.uint8), 2)[order]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.jsm"
            split = root / "split.jsm"
            original.write_bytes(b"JSM2" + struct.pack("<I", len(rows)) + rows.tobytes())
            split.write_bytes(
                b"JSM2" + struct.pack("<I", len(rows)) + rows[order].tobytes()
            )
            recovered = recover_split_cell_ids(
                original_meta_path=original,
                split_meta_path=split,
                quotas=quotas,
                split_seed=seed,
                holdout_mod=10,
            )
        np.testing.assert_array_equal(recovered, expected)


if __name__ == "__main__":
    unittest.main()
