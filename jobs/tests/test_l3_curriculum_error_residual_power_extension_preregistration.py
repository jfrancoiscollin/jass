#!/usr/bin/env python3
import copy
import unittest

from jobs.tools import l3_curriculum_error_residual_power_extension_preregistration as target
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge


def candidate(alpha, lower, mean, *, paired_pass=False, extra_failure=None):
    gates = {
        "error_interventions_at_least_12": True,
        "control_interventions_at_least_8": True,
        "total_interventions_at_least_20": True,
        "error_positive_realization_rate_ge_0_60": True,
        "control_mean_gain_ge_minus_2cp": True,
        target.PAIRED_GATE: paired_pass,
        "minimum_coefficient_cosine_ge_0_75": True,
        "minimum_top5_jaccard_ge_0_40": True,
        "minimum_fold_decision_jaccard_ge_0_50": True,
        "outside_gate_bit_identical": True,
    }
    if extra_failure:
        gates[extra_failure] = False
    failed = sorted(key for key, value in gates.items() if not value)
    return {
        "alpha": alpha,
        "cap_cp": 150.0,
        "mode": "at_least_one_change",
        "threshold_cp": 0.0,
        "metrics": {
            "error_interventions": 18,
            "control_interventions": 14,
            "error_positive_realization_rate": 0.72,
            "error_improvement": {"mean": 900.0, "ci95": [10.0, 1700.0]},
            "control_improvement": {"mean": 100.0, "ci95": [-50.0, 250.0]},
            "paired_error_minus_control": {"mean": mean, "ci95": [lower, 1800.0]},
        },
        "stability": {
            "minimum_coefficient_cosine": 0.9,
            "minimum_top5_feature_jaccard": 0.8,
            "minimum_fold_decision_jaccard": 0.7,
        },
        "plateau": {"minimum_neighbor_intervention_jaccard": 0.8},
        "base_gates": gates,
        "base_passed": all(gates.values()),
        "plateau_gate": True,
        "passed": paired_pass and extra_failure is None,
        "failed_gates": failed,
        "intervention_set_sha256": f"set-{alpha}-{lower}",
    }


def inputs():
    rows = [
        candidate(0.3, -120.0, 840.0),
        candidate(1.0, -80.0, 700.0),
        candidate(3.0, -10.0, 1200.0, extra_failure="minimum_top5_jaccard_ge_0_40"),
    ]
    screen = {
        "schema": ridge.SCHEMA,
        "verdict": ridge.NOT_ESTABLISHED,
        "passed": False,
        "passing_candidates": 0,
        "selected": None,
        "sham": None,
        "candidates": rows,
    }
    for key in (
        "feature_audit_profile_rows_examined",
        "feature_audit_action_value_reads",
        "outer_confirm_action_value_reads",
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        screen[key] = 0
    audit = {
        "schema": target.AUDIT_SCHEMA,
        "verdict": target.AUDIT_READY,
        "passed": True,
        "scientific_passed": False,
        "family_closed": True,
        "mechanism": "PAIRED_EFFECT_NOT_ESTABLISHED_DESPITE_OTHER_GATES",
        "source": {
            "job": "screen",
            "attempt": "sa",
            "code_sha": "sc",
            "verdict": ridge.NOT_ESTABLISHED,
        },
        "candidates_passing_all_except_paired": 2,
        "fits": 0,
        "new_targets": 0,
        "holdout_reads": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    return screen, audit, ("screen", "sa", "sc"), ("audit", "aa", "ac")


class ResidualPowerExtensionPreregistrationTests(unittest.TestCase):
    def test_selects_only_all_except_paired_by_frozen_rule(self):
        report = target.preregister(*inputs())
        self.assertEqual(report["eligible_hypotheses"], 2)
        self.assertEqual(report["selected_hypothesis"]["alpha"], 1.0)
        self.assertEqual(
            report["selected_hypothesis"]["training_evidence"]["failed_gates"],
            [target.PAIRED_GATE],
        )
        self.assertEqual(
            report["protocol"]["fresh_pair_mining"]["pair_count_exact"], 300
        )

    def test_fresh_extension_is_confirmation_not_refit(self):
        report = target.preregister(*inputs())
        training = report["protocol"]["model_training"]
        self.assertFalse(training["fresh_extension_labels_used_for_fit"])
        self.assertFalse(training["feature_audit_or_outer_confirm_used_for_fit"])
        self.assertEqual(report["holdout_reads"], 0)
        self.assertFalse(report["fresh_target_reconstruction_authorized"])
        self.assertFalse(report["production_rule_authorized"])

    def test_candidate_count_or_source_chain_drift_fails_closed(self):
        screen, audit, sid, aid = inputs()
        audit["candidates_passing_all_except_paired"] = 3
        with self.assertRaisesRegex(ValueError, "count drift"):
            target.preregister(screen, audit, sid, aid)
        screen, audit, sid, aid = inputs()
        audit["source"]["attempt"] = "wrong"
        with self.assertRaisesRegex(ValueError, "identity chain drift"):
            target.preregister(screen, audit, sid, aid)

    def test_any_holdout_read_fails_closed(self):
        screen, audit, sid, aid = inputs()
        audit["holdout_reads"] = 1
        with self.assertRaisesRegex(ValueError, "counter drift"):
            target.preregister(screen, audit, sid, aid)


if __name__ == "__main__":
    unittest.main()
