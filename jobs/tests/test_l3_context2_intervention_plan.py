# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS
from jobs.tools.l3_context2_intervention_plan import (
    GENERATOR_CELLS,
    NON_GENERATOR_CONTROLS,
    _parse_cells,
    build_plan,
)


def cell_report(index: int) -> dict:
    width = len(CTX2_BASE_COMPONENTS)
    means = np.linspace(-0.03, 0.03, width) + index * 0.001
    standard = np.linspace(0.08, 0.22, width)
    standard[(index * 3) % width] *= 1.0 + 0.30 * index
    corr = np.eye(width)
    corr[0, 1] = corr[1, 0] = max(0.05, 0.72 - 0.08 * index)
    rows = {}
    for component, mean, std in zip(CTX2_BASE_COMPONENTS, means, standard):
        rows[component] = {
            "mean": float(mean),
            "rms": float(np.sqrt(mean * mean + std * std)),
            "active_position_rate_material": 0.35 + 0.01 * index,
            "positive_position_rate": 0.18 + 0.004 * index,
            "negative_position_rate": 0.17 + 0.004 * index,
        }
    return {
        "schema": "jass.l3_context2_activation_census.v1",
        "population": {
            "positions": 250_000,
            "wdl_stm_rates": {"-1": 0.42, "0": 0.16 + index * 0.003, "1": 0.42 - index * 0.003},
        },
        "phase": {
            "tempo_mid_weight_mean": 0.12 + index * 0.001,
            "strata": [
                {"position_rate": value}
                for value in (0.12, 0.18, 0.24, 0.25, 0.21)
            ],
        },
        "base_15_signals": rows,
        "diagnostics": {"base_matrix": {"correlation": corr.tolist()}},
    }


def contribution_audit() -> dict:
    return {
        "schema": "jass.l3_context2_fixed_contribution_audit.v1",
        "verdict": "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY",
        "cohorts": {"train_oof": {"base_15_concentration": {
            "largest_share": 0.57,
            "top3_share": 0.77,
            "effective_component_count": 2.8,
        }}},
    }


def attribution() -> dict:
    guards = {
        name: {"passed": name != "NODECAY"}
        for name in (*GENERATOR_CELLS, *NON_GENERATOR_CONTROLS)
    }
    return {
        "schema": "jass.l3_context2_knob_attribution_job.v1",
        "verdict": "JASS_CONTEXT2_KNOB_ATTRIBUTION_READY",
        "records_per_cell": 250_000,
        "guards": guards,
    }


class Context2InterventionPlanTests(unittest.TestCase):
    def reports(self) -> dict[str, dict]:
        names = (*GENERATOR_CELLS, *NON_GENERATOR_CONTROLS)
        return {name: cell_report(index) for index, name in enumerate(names)}

    def test_builds_deterministic_guarded_two_million_record_plan(self) -> None:
        kwargs = dict(
            attribution_summary=attribution(),
            contribution_audit=contribution_audit(),
            cell_reports=self.reports(),
            total_records=2_000_000,
            step=0.05,
            min_base_weight=0.15,
            min_intervention_weight=0.05,
            max_cell_weight=0.30,
            max_relative_draw_shift=0.15,
            max_wdl_side_skew=0.04,
            max_relative_tempo_mid_shift=0.15,
        )
        first = build_plan(**kwargs)
        second = build_plan(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(sum(first["corpus"]["record_quotas"].values()), 2_000_000)
        self.assertEqual(set(first["corpus"]["weights"]), set(GENERATOR_CELLS))
        self.assertNotIn("NODECAY", first["corpus"]["weights"])
        self.assertGreaterEqual(first["corpus"]["weights"]["BASE"], 0.15)
        self.assertTrue(all(value >= 0.05 for value in first["corpus"]["weights"].values()))
        self.assertTrue(first["generation_authorized_by_design"])
        self.assertGreater(first["predicted_design"]["logdet_gain_vs_base"], 0.0)
        self.assertLessEqual(
            first["predicted_design"]["relative_tempo_mid_shift_vs_base"], 0.15
        )
        self.assertFalse(first["selfplay_generated"])
        self.assertFalse(first["promotion_authorized"])

    def test_rejects_nodecay_if_its_guard_rationale_drifts(self) -> None:
        source = attribution()
        source["guards"]["NODECAY"]["passed"] = True
        with self.assertRaisesRegex(ValueError, "NODECAY unexpectedly passed"):
            build_plan(
                attribution_summary=source,
                contribution_audit=contribution_audit(),
                cell_reports=self.reports(),
                total_records=2_000_000,
                step=0.05,
                min_base_weight=0.15,
                min_intervention_weight=0.05,
                max_cell_weight=0.30,
                max_relative_draw_shift=0.15,
                max_wdl_side_skew=0.04,
                max_relative_tempo_mid_shift=0.15,
            )

    def test_cell_cli_parser_requires_exact_audited_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = []
            for index, name in enumerate((*GENERATOR_CELLS, *NON_GENERATOR_CONTROLS)):
                path = root / f"{name}.json"
                path.write_text(json.dumps(cell_report(index)), encoding="utf-8")
                items.append(f"{name}={path}")
            self.assertEqual(set(_parse_cells(items)), set((*GENERATOR_CELLS, *NON_GENERATOR_CONTROLS)))
            with self.assertRaisesRegex(ValueError, "cell set drift"):
                _parse_cells(items[:-1])


if __name__ == "__main__":
    unittest.main()
