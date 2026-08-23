#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from jobs.tools import l3_curriculum_error_anchored_local_refit_preregistration as target
from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_residual_stable_subspace_screen as subspace


IDENTITIES = {
    "champion_sha256": "champion",
    "jass_sha256": "jass",
    "search_params_sha256": "search",
}


def _confirmation() -> dict:
    return {
        "schema": confirmation.SCHEMA_TERMINAL,
        "verdict": confirmation.READY,
        "passed": True,
        "fresh_pairs": 600,
        "fresh_labels_used_for_fit": False,
        "anchored_local_refit_preregistration_authorized": True,
        "failed_gates": [],
        "gates": {"all": True},
        "selected_hypothesis": {
            "alpha": 300.0,
            "cap_cp": 100.0,
            "mode": "strict_both_change",
            "threshold_cp": 10.0,
        },
        "rule_proof": {
            "endgame_interventions": 0,
            "endgame_decisions_bit_identical_to_anchor": True,
            "non_endgame_decisions_bit_identical_to_frozen_residual": True,
        },
        "identities": IDENTITIES,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }


def _subspace() -> dict:
    rows = [
        {
            "index": index,
            "name": f"feature-{index}",
            "sign": 1,
            "selected": True,
        }
        for index in range(4)
    ]
    return {
        "schema": target.SUBSPACE_TERMINAL_SCHEMA,
        "verdict": subspace.READY,
        "passed": True,
        "stable_subspace_candidate_established": True,
        "alpha": 300.0,
        "failed_gates": [],
        "gates": {"all": True},
        "analysis": {
            "selected_feature_names": [row["name"] for row in rows],
            "selected_feature_indices": [row["index"] for row in rows],
            "selected_feature_count": len(rows),
            "support_sha256": "a" * 64,
            "features": rows,
        },
        **IDENTITIES,
        "new_exact_target_computations": 0,
        "fresh_label_reads": 0,
        "feature_audit_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }


class AnchoredLocalRefitPreregistrationTests(unittest.TestCase):
    def test_joint_pass_freezes_one_strongly_anchored_hypothesis(self) -> None:
        report = target.preregister(
            _confirmation(),
            _subspace(),
            ("confirmation", "attempt-c", "code-c"),
            ("subspace", "attempt-s", "code-s"),
        )

        self.assertEqual(report["verdict"], target.READY)
        self.assertEqual(report["support"]["feature_count"], 4)
        self.assertEqual(report["protocol"]["fit"]["candidate_models"], 1)
        self.assertFalse(report["protocol"]["fit"]["hyperparameter_search"])
        self.assertEqual(
            report["protocol"]["fit"]["all_other_coefficients"],
            "bit_identical_to_full_1508_alpha300_model",
        )
        self.assertEqual(
            report["protocol"]["base_champion"]["pattern_eval_bytes"],
            "must_remain_sha256_identical",
        )
        self.assertEqual(report["new_targets"], 0)
        self.assertEqual(report["oos_reads"], 0)
        self.assertTrue(report["anchored_local_refit_authorized"])
        self.assertFalse(report["oos_campaign_authorized"])
        self.assertFalse(report["strength_gate_authorized"])
        self.assertFalse(report["automatic_continuation"])

    def test_negative_confirmation_fails_closed(self) -> None:
        report = _confirmation()
        report["passed"] = False
        with self.assertRaisesRegex(ValueError, "passed 600-pair confirmation"):
            target.preregister(report, _subspace(), ("c", "a", "s"), ("s", "a", "s"))

    def test_unstable_or_malformed_support_fails_closed(self) -> None:
        report = _subspace()
        report["analysis"]["selected_feature_count"] = 9
        with self.assertRaisesRegex(ValueError, "support drift"):
            target.preregister(_confirmation(), report, ("c", "a", "s"), ("s", "a", "s"))

    def test_scientific_identity_drift_fails_closed(self) -> None:
        report = copy.deepcopy(_subspace())
        report["champion_sha256"] = "other"
        with self.assertRaisesRegex(ValueError, "identity drift"):
            target.preregister(_confirmation(), report, ("c", "a", "s"), ("s", "a", "s"))

    def test_any_forbidden_upstream_action_fails_closed(self) -> None:
        report = _confirmation()
        report["strength_games"] = 1
        with self.assertRaisesRegex(ValueError, "forbidden counter drift"):
            target.preregister(report, _subspace(), ("c", "a", "s"), ("s", "a", "s"))


if __name__ == "__main__":
    unittest.main()
