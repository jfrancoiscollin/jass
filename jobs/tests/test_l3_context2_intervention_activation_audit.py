# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS
from jobs.tools.l3_context2_intervention_activation_audit import audit


def activation(correlation: float, scale: float) -> dict:
    width = len(CTX2_BASE_COMPONENTS)
    corr = np.eye(width)
    corr[0, 1] = corr[1, 0] = correlation
    rows = {
        name: {
            "mean": 0.001 * index,
            "rms": scale * (1.0 + index / width),
            "active_position_rate_material": 0.2 + index / 100.0,
            "positive_position_rate": 0.11,
            "negative_position_rate": 0.09,
        }
        for index, name in enumerate(CTX2_BASE_COMPONENTS)
    }
    return {
        "schema": "jass.l3_context2_activation_census.v1",
        "population": {
            "positions": 2_000_000,
            "games": 100_000,
            "openings": 50_000,
            "wdl_stm_rates": {"-1": 0.42, "0": 0.16, "1": 0.42},
        },
        "phase": {
            "tempo_mid_weight_mean": 0.1,
            "recomposition_max_absolute_error": 1e-7,
            "strata": [{"position_rate": 0.2} for _ in range(5)],
        },
        "base_15_signals": rows,
        "diagnostics": {
            "all_30_channels_materially_active": True,
            "all_15_base_signals_materially_active": True,
            "rare_raw_channels": [],
            "rare_base_signals": [],
            "base_matrix": {"correlation": corr.tolist()},
        },
    }


def plan() -> dict:
    return {
        "schema": "jass.l3_context2_intervention_plan.v1",
        "verdict": "JASS_CONTEXT2_INTERVENTION_PLAN_READY",
        "constraints": {
            "maximum_relative_draw_shift_vs_base": 0.15,
            "maximum_wdl_side_skew": 0.02,
        },
        "predicted_design": {"logdet_gain_vs_base": 0.2},
    }


def contribution() -> dict:
    return {
        "schema": "jass.l3_context2_fixed_contribution_audit.v1",
        "cohorts": {"train_oof": {"base_15_concentration": {
            "largest_share": 0.57,
            "top3_share": 0.77,
            "effective_component_count": 2.803,
        }}},
    }


class Context2InterventionActivationAuditTests(unittest.TestCase):
    def test_passes_realized_covariance_screen(self) -> None:
        result = audit(
            intervention=activation(0.2, 0.3),
            baseline=activation(0.8, 0.1),
            corpus={
                "schema": "jass.l3_context2_intervention_corpus.v1",
                "verdict": "JASS_CONTEXT2_INTERVENTION_CORPUS_READY",
                "records": 2_000_000,
                "relative_draw_shift_vs_base": 0.01,
                "wdl_side_skew": 0.002,
            },
            plan=plan(),
            current_contribution=contribution(),
        )
        self.assertTrue(result["screen_passed"])
        self.assertGreater(result["realized"]["logdet_gain_vs_base"], 0.0)
        self.assertFalse(result["patterneval_fit_authorized"])
        self.assertEqual(
            result["next_required_stage"],
            "aligned mapper contribution/concentration screen on intervention corpus",
        )

    def test_fails_closed_when_a_channel_is_missing(self) -> None:
        intervention = activation(0.2, 0.3)
        intervention["diagnostics"]["all_30_channels_materially_active"] = False
        result = audit(
            intervention=intervention,
            baseline=activation(0.8, 0.1),
            corpus={
                "schema": "jass.l3_context2_intervention_corpus.v1",
                "verdict": "JASS_CONTEXT2_INTERVENTION_CORPUS_READY",
                "records": 2_000_000,
                "relative_draw_shift_vs_base": 0.01,
                "wdl_side_skew": 0.002,
            },
            plan=plan(),
            current_contribution=contribution(),
        )
        self.assertFalse(result["screen_passed"])
        self.assertIn("FAILED", result["verdict"])


if __name__ == "__main__":
    unittest.main()
