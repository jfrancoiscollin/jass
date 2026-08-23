import unittest

from jobs.tools import l3_curriculum_error_endgame_abstention_preregistration as prereg


def audit():
    gates = {
        "adjusted_error_mean_positive": True,
        "adjusted_paired_mean_positive": True,
        "adjusted_control_mean_at_least_minus_2cp": True,
        "pool1_adjusted_error_mean_positive": True,
        "pool1_adjusted_paired_mean_positive": True,
        "pool1_adjusted_control_mean_at_least_minus_2cp": True,
        "pool2_adjusted_error_mean_positive": True,
        "pool2_adjusted_paired_mean_positive": True,
        "pool2_adjusted_control_mean_at_least_minus_2cp": True,
        "remaining_error_positive_rate_at_least_0_60": True,
    }
    return {
        "schema": prereg.AUDIT_SCHEMA,
        "verdict": prereg.AUDIT_READY,
        "passed": True,
        "rule": "abstain_when_phase_equals_endgame",
        "status": "posthoc_discovery_only_not_confirmed",
        "fresh_1517_reuse_for_validation_forbidden": True,
        "preregistration_on_new_fresh_pools_recommended": True,
        "gates": gates,
        "source_identity": {"job_id": "source-j", "attempt_id": "source-a", "code_sha": "source-c"},
        "baseline_global": {}, "adjusted_global": {}, "baseline_by_pool": {},
        "adjusted_by_pool": {}, "removed_interventions": {"error": 15, "control": 15},
        "remaining_error_positive_realization_rate": .818182,
        "production_refit_authorized": False, "strength_gate_authorized": False,
        "promotion_authorized": False, "automatic_continuation": False,
        "new_exact_targets": 0, "fits": 0, "strength_games": 0,
        "new_selfplay": 0, "frozen_reads": 0,
    }


class EndgameAbstentionPreregistrationTests(unittest.TestCase):
    def test_freezes_one_rule_and_new_pool_confirmation(self):
        report = prereg.preregister(
            audit(), ("audit-j", "audit-a", "audit-c"),
            ("source-j", "source-a", "source-c"),
        )
        self.assertEqual(report["verdict"], prereg.READY)
        self.assertEqual(report["protocol"]["fresh_pair_mining"]["pair_count_exact"], 600)
        self.assertEqual(report["protocol"]["fresh_campaign"]["games_exact"], 15360)
        self.assertEqual(report["frozen_hypothesis"]["phase_rule"]["abstain_exact_value"], "endgame")
        self.assertTrue(report["fresh_pair_availability_authorized"])
        self.assertFalse(report["fresh_target_reconstruction_authorized"])
        self.assertFalse(report["production_refit_authorized"])
        self.assertEqual(report["discovery_audit_source"]["job"], "audit-j")
        self.assertEqual(report["discovery_data_source"]["job"], "source-j")

    def test_rejects_any_failed_discovery_gate(self):
        row = audit(); row["gates"]["pool1_adjusted_paired_mean_positive"] = False
        with self.assertRaisesRegex(ValueError, "gates"):
            prereg.preregister(row, ("audit-j", "audit-a", "audit-c"), ("source-j", "source-a", "source-c"))

    def test_rejects_validation_reuse_or_source_drift(self):
        row = audit(); row["fresh_1517_reuse_for_validation_forbidden"] = False
        with self.assertRaisesRegex(ValueError, "reuse"):
            prereg.preregister(row, ("audit-j", "audit-a", "audit-c"), ("source-j", "source-a", "source-c"))
        with self.assertRaisesRegex(ValueError, "identity"):
            prereg.preregister(audit(), ("audit-j", "audit-a", "audit-c"), ("wrong", "source-a", "source-c"))


if __name__ == "__main__":
    unittest.main()
