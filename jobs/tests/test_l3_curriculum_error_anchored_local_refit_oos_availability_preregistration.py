from __future__ import annotations

import copy
import unittest

from jobs.tools import l3_curriculum_error_anchored_local_refit as anchored
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability_preregistration as registration
from jobs.tools import l3_curriculum_error_anchored_local_refit_preregistration as joint


IDENTITIES = {
    "champion_sha256": "a" * 64,
    "jass_sha256": "b" * 64,
    "search_params_sha256": "c" * 64,
}


def model() -> dict:
    return {
        "schema": anchored.MODEL_SCHEMA,
        "identities": copy.deepcopy(IDENTITIES),
        "support_sha256": "d" * 64,
        "authorized_for_oos_audit": True,
        "authorized_for_strength": False,
        "authorized_for_promotion": False,
    }


def fit_report(candidate: dict) -> dict:
    return {
        "schema": "jass.curriculum_error_anchored_local_refit_terminal.v1",
        "verdict": anchored.READY,
        "passed": True,
        "identities": copy.deepcopy(IDENTITIES),
        "support": {"support_sha256": "d" * 64},
        "model_sha256": registration._digest(candidate),
        "oos_labels_used_for_fit": False,
        "oos_availability_preregistration_authorized": True,
        "strength_gate_authorized": False,
        "failed_gates": [],
        "gates": {"all": True},
        "model_candidates_fit": 1,
        "residual_production_fits": 1,
        "pattern_eval_fits": 0,
        "oos_reads": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }


def joint_report() -> dict:
    return {
        "schema": "jass.curriculum_error_anchored_local_refit_preregistration_terminal.v1",
        "verdict": joint.READY,
        "passed": True,
        "identities": copy.deepcopy(IDENTITIES),
        "support": {"support_sha256": "d" * 64},
        "anchored_local_refit_authorized": True,
        "oos_campaign_authorized": False,
        "strength_gate_authorized": False,
        "automatic_continuation": False,
        "protocol": {
            "sealed_oos": {
                "pair_count_exact": joint.OOS_PAIRS,
                "two_pools": True,
                "pool1_seed": joint.OOS_POOL1_SEED,
                "pool2_seed": joint.OOS_POOL2_SEED,
                "split_seed": joint.OOS_SPLIT_SEED,
                "target_free_candidate_order": True,
                "maximum_states_per_source_game": 2,
                "canonical_state_unique": True,
                "no_oos_label_used_for_fit_or_selection": True,
            }
        },
    }


def exclusions() -> list[dict[str, str]]:
    return [
        {"role": role, "job": f"cpx62-{1504 + index}-source", "attempt": f"attempt-{index}", "code_sha": f"{index + 1:040x}"}
        for index, role in enumerate(registration.REQUIRED_EXCLUSION_ROLES)
    ]


class AnchoredOosAvailabilityPreregistrationTests(unittest.TestCase):
    def test_seals_campaign_before_oos_games_or_labels(self) -> None:
        candidate = model()
        report = registration.preregister(
            joint_report(),
            fit_report(candidate),
            candidate,
            ("joint-job", "joint-attempt", "1" * 40),
            ("fit-job", "fit-attempt", "2" * 40),
            exclusions(),
        )
        self.assertEqual(report["verdict"], registration.READY)
        self.assertTrue(report["fresh_pair_availability_authorized"])
        self.assertFalse(report["fresh_target_reconstruction_authorized"])
        self.assertEqual(report["new_targets"], 0)
        self.assertEqual(report["oos_reads"], 0)
        campaign = report["protocol"]["fresh_campaign"]
        self.assertEqual(campaign["games_exact"], 15360)
        self.assertEqual(campaign["pool_seeds"], [joint.OOS_POOL1_SEED, joint.OOS_POOL2_SEED])
        mining = report["protocol"]["fresh_pair_mining"]
        self.assertEqual(mining["pair_count_per_pool_exact"], 300)
        self.assertEqual(mining["stop_rule"], "first_300_valid_pairs_per_pool_in_frozen_pre_target_order")

    def test_rejects_any_prior_oos_read(self) -> None:
        candidate = model()
        fit = fit_report(candidate)
        fit["oos_reads"] = 1
        with self.assertRaisesRegex(ValueError, "forbidden counter"):
            registration.preregister(
                joint_report(), fit, candidate,
                ("joint-job", "joint-attempt", "1" * 40),
                ("fit-job", "fit-attempt", "2" * 40),
                exclusions(),
            )

    def test_requires_complete_unique_exclusion_chain(self) -> None:
        candidate = model()
        with self.assertRaisesRegex(ValueError, "roles are incomplete"):
            registration.preregister(
                joint_report(), fit_report(candidate), candidate,
                ("joint-job", "joint-attempt", "1" * 40),
                ("fit-job", "fit-attempt", "2" * 40),
                exclusions()[:-1],
            )


if __name__ == "__main__":
    unittest.main()
