import unittest

from jobs.tools import l3_curriculum_error_action_flip_tail_autopsy as autopsy


def _detail(pair_id, pool, role, *, gain, clipped=False, intervene=True):
    return {
        "pair_id": pair_id,
        "source_pool": pool,
        "role": role,
        "intervention": intervene,
        "improvement_cp": gain if intervene else 0.0,
        "predicted_advantage_cp": 12.0 if intervene else None,
        "guard_margin_cp": 7.0 if intervene else None,
        "correction_clipped": clipped,
        "anchor_disagreement": False,
        "proposed_capture": False,
        "original_anchor_margin_cp": 10.0,
        "image_anchor_margin_cp": 10.0,
        "piece_count": 16,
        "phase": "middle",
    }


class ActionFlipTailAutopsyTests(unittest.TestCase):
    def test_risk_flags_use_only_predecision_descriptors(self):
        row = _detail(1, "pool1", "error", gain=-100.0, clipped=True)
        flags = autopsy._risk_flags(row)
        self.assertTrue(flags["predicted_advantage_lt_15cp"])
        self.assertFalse(flags["guard_margin_lt_5cp"])
        self.assertTrue(flags["correction_clipped"])
        self.assertNotIn("improvement", " ".join(flags))

    def test_counterfactual_is_paired_and_pool_specific(self):
        rows = []
        for pool_index, pool in enumerate(("pool1", "pool2")):
            for index in range(10):
                pair_id = pool_index * 100 + index
                rows.append(_detail(
                    pair_id, pool, "error",
                    gain=-100.0 if index == 0 else 25.0,
                    clipped=index == 0,
                ))
                rows.append(_detail(pair_id, pool, "control", gain=0.0, intervene=False))
        result = autopsy._counterfactual(rows, "correction_clipped")
        self.assertEqual(result["removed_interventions"]["error"], 2)
        self.assertEqual(result["retained_error_interventions_by_pool"], {"pool1": 9, "pool2": 9})
        self.assertEqual(result["retained_error_positive_realization_rate"], 1.0)
        self.assertGreater(result["minimum_pool_paired_mean_cp"], 0.0)
        self.assertTrue(result["descriptive_stability_gates_pass"])

    def test_source_must_be_negative_and_non_authorizing(self):
        bucket = {"bucket": "negative"}
        report = {
            "schema": autopsy.SOURCE_SCHEMA,
            "verdict": autopsy.action.READY,
            "passed": True,
            "scientific_sources": {"bucket_report_sha256": autopsy._digest(bucket)},
            "action_margin_screen": {
                "passed": False,
                "status": "action_margin_correction_not_established",
                "best_candidate": {"config": {"name": autopsy.EXPECTED_BEST}},
            },
            "new_fresh_pool_preregistration_recommended": False,
            "anchored_local_refit_authorized": False,
            "production_model_authorized": False,
            "strength_gate_authorized": False,
            "promotion_authorized": False,
            "automatic_continuation": False,
        }
        config = autopsy._require_source(report, bucket)
        self.assertEqual(config["name"], autopsy.EXPECTED_BEST)
        report["action_margin_screen"]["passed"] = True
        with self.assertRaises(ValueError):
            autopsy._require_source(report, bucket)


if __name__ == "__main__":
    unittest.main()
