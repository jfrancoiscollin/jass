#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_action_ranker_oof_autopsy as autopsy


def metric(mean: float, probability: float = 0.5) -> dict:
    return {"n": 103, "mean": mean, "ci95": [mean - 1, mean + 1], "probability_positive": probability}


def candidate(alpha: float, threshold: float, margin: float, paired: float) -> dict:
    gates = {
        "error_probability_positive_ge_0_90": paired > 0,
        "paired_probability_positive_ge_0_90": False,
        "controls_not_harmed_mean": paired > 0,
        "at_least_12_error_pairs_changed": True,
        "candidate_symmetry_ge_0_70": True,
        "candidate_symmetry_not_worse": True,
    }
    return {
        "alpha": alpha,
        "advantage_threshold_cp": threshold,
        "margin_band_cp": margin,
        "selection_score": paired,
        "oof_passed": False,
        "oof_gates": gates,
        "oof": {
            "error_improvement": metric(paired),
            "control_improvement": metric(0),
            "paired_error_minus_control": metric(paired),
            "error_changed_pairs": 12,
            "control_changed_pairs": 1,
            "error_baseline_symmetry": 1.0,
            "error_candidate_symmetry": 1.0,
            "control_baseline_symmetry": 1.0,
            "control_candidate_symmetry": 1.0,
            "error_rate_reduction": metric(0),
            "teacher_hit_gain": metric(0),
        },
    }


def source_report() -> dict:
    rows = []
    for alpha in ranker.RIDGE_ALPHAS:
        for threshold in ranker.ADVANTAGE_THRESHOLDS_CP:
            for margin in ranker.MARGIN_BANDS_CP:
                rows.append(candidate(alpha, threshold, margin, 1 if alpha == 100 else -1))
    return {
        "schema": ranker.SCHEMA,
        "verdict": autopsy.EXPECTED_NEGATIVE,
        "passed": False,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "selected_candidate": None,
        "sham": None,
        "inner_validation": None,
        "inner_validation_gates": {},
        "outer_confirm": None,
        "outer_confirm_gates": {},
        "outer_confirm_pairs_read": 0,
        "support": {"discovery": 134, "inner_fit": 103, "inner_validation": 31, "outer_confirm": None},
        "inner_split": {"overlap": 0},
        "candidates": rows,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "production_rule_authorized": False,
    }


def source_model() -> dict:
    return {
        "schema": ranker.MODEL_SCHEMA,
        "authorized_for_implementation": False,
        "hyperparameters": None,
        "model": None,
    }


class ActionRankerOOFAutopsyTests(unittest.TestCase):
    def test_audit_preserves_both_sealed_holdouts(self):
        result = autopsy.analyze(source_report(), source_model())
        self.assertEqual(result["candidate_count"], 27)
        self.assertEqual(result["positive_paired_mean_candidate_count"], 9)
        self.assertEqual(result["validation_decision_payload_reads"], 0)
        self.assertEqual(result["outer_confirm_decision_payload_reads"], 0)
        self.assertFalse(result["production_rule_authorized"])

    def test_rejects_any_prior_validation_read(self):
        report = source_report()
        report["inner_validation"] = {"pairs": 31}
        with self.assertRaisesRegex(ValueError, "inner validation"):
            autopsy.analyze(report, source_model())

    def test_rejects_incomplete_grid(self):
        report = source_report()
        report["candidates"].pop()
        with self.assertRaisesRegex(ValueError, "grid coverage"):
            autopsy.analyze(report, source_model())


if __name__ == "__main__":
    unittest.main()
