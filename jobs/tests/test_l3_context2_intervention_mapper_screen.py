# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import unittest

from jobs.tools.l3_context2_intervention_mapper_screen import screen


def contribution(top1: float, top3: float, effective: float) -> dict:
    return {
        "schema": "jass.l3_context2_fixed_contribution_audit.v1",
        "verdict": "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY",
        "cohorts": {"train_oof": {"base_15_concentration": {
            "largest_share": top1,
            "top3_share": top3,
            "effective_component_count": effective,
        }}},
    }


ACTIVATION = {
    "schema": "jass.l3_context2_intervention_activation_audit.v1",
    "screen_passed": True,
}


class Context2InterventionMapperScreenTests(unittest.TestCase):
    def test_passes_all_three_preregistered_ratios(self) -> None:
        result = screen(
            intervention=contribution(0.50, 0.70, 3.60),
            current=contribution(0.573462, 0.766677, 2.803),
            activation=ACTIVATION,
        )
        self.assertTrue(result["screen_passed"])
        self.assertTrue(result["patterneval_fit_authorized"])
        self.assertTrue(all(result["guards"].values()))

    def test_fails_if_only_two_of_three_ratios_pass(self) -> None:
        result = screen(
            intervention=contribution(0.50, 0.70, 3.40),
            current=contribution(0.573462, 0.766677, 2.803),
            activation=ACTIVATION,
        )
        self.assertFalse(result["screen_passed"])
        self.assertFalse(result["guards"]["effective_count_at_least_125pct_current"])
        self.assertFalse(result["patterneval_fit_authorized"])

    def test_rejects_unpassed_activation_screen(self) -> None:
        activation = dict(ACTIVATION, screen_passed=False)
        with self.assertRaisesRegex(ValueError, "did not pass"):
            screen(
                intervention=contribution(0.50, 0.70, 3.60),
                current=contribution(0.573462, 0.766677, 2.803),
                activation=activation,
            )


if __name__ == "__main__":
    unittest.main()
