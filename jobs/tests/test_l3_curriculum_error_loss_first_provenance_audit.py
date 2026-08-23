import unittest

from jobs.tools import l3_curriculum_error_loss_first_provenance_audit as audit


def source_report():
    details = []
    for index in range(272):
        if index < 113:
            gain = -30000.0 if index == 0 else (-10000.0 if index < 3 else -10.0)
        elif index < 265:
            gain = 20.0
        else:
            gain = 0.0
        details.append({
            "pair_id": index,
            "source_pool": "pool1" if index < 136 else "pool2",
            "role": "error", "improvement_cp": gain, "phase": "middle",
            "piece_count": 14, "outcome": "loss", "predicted_advantage_cp": 12.0,
            "guard_margin_cp": 7.0, "correction_clipped": False,
            "anchor_disagreement": False, "proposed_capture": False,
            "exact_teacher_hit": gain > 0.0, "exact_anchor_regret_cp": 60.0,
            "dominant_feature": "rank_fraction_d6", "dominant_feature_family": "rank",
            "feature_contributions_cp": {"rank_fraction_d6": 10.0},
        })
    for index in range(309):
        details.append({
            "pair_id": index,
            "source_pool": "pool1" if index < 154 else "pool2",
            "role": "control", "improvement_cp": 1.0, "phase": "middle",
            "piece_count": 14, "outcome": "draw", "predicted_advantage_cp": 12.0,
            "guard_margin_cp": 7.0, "correction_clipped": False,
            "anchor_disagreement": False, "proposed_capture": False,
            "exact_teacher_hit": False, "exact_anchor_regret_cp": 0.0,
            "dominant_feature": "rank_fraction_d6", "dominant_feature_family": "rank",
            "feature_contributions_cp": {"rank_fraction_d6": 10.0},
        })
    total_loss = -sum(row["improvement_cp"] for row in details if row["role"] == "error" and row["improvement_cp"] < 0)
    losses = sorted([-row["improvement_cp"] for row in details if row["role"] == "error" and row["improvement_cp"] < 0], reverse=True)
    return {
        "schema": audit.SOURCE_SCHEMA, "code_sha": audit.SOURCE_CODE,
        "verdict": audit.SOURCE_VERDICT, "passed": True,
        "next_stage": "design_loss_first_corpus", "descriptively_stable_counterfactuals": [],
        "counts": dict(audit.EXPECTED_COUNTS), "detailed_interventions": details,
        "loss_concentration": {"total_loss_cp": total_loss, "top_1_share": losses[0]/total_loss, "top_3_share": sum(losses[:3])/total_loss},
        "candidate_reproduction": {"by_pool": {"pool1": {"pairs": 300}, "pool2": {"pairs": 300}}},
        "feature_attribution": {"negative_error_interventions": [{"name": "rank_fraction_d6", "mean_absolute_cp": 10.0, "mean_signed_cp": 10.0}]},
        "new_exact_target_computations": 0, "pattern_eval_fits": 0,
        "production_model_fits": 0, "strength_games": 0,
        "new_selfplay_games": 0, "frozen_reads": 0,
        "anchored_local_refit_authorized": False, "production_model_authorized": False,
        "strength_gate_authorized": False, "promotion_authorized": False,
        "automatic_continuation": False,
    }


class ProvenanceAuditTest(unittest.TestCase):
    def test_tail_and_guards(self):
        report = audit.audit(source_report())
        self.assertTrue(report["loss_tail"]["score_scale_tail_dominated"])
        self.assertEqual(report["loss_tail"]["sentinel_scale_loss_count"], 3)
        self.assertEqual(report["next_stage"], "preregister_loss_first_sibling_rank_corpus")
        self.assertFalse(report["anchored_local_refit_authorized"])
        self.assertEqual(report["worst_error_interventions"][0]["pair_id"], 0)

    def test_rejects_authorization_drift(self):
        source = source_report(); source["strength_gate_authorized"] = True
        with self.assertRaisesRegex(ValueError, "authorization drift"):
            audit.audit(source)


if __name__ == "__main__":
    unittest.main()
