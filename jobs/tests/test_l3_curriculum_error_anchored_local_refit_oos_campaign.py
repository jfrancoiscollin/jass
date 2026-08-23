from __future__ import annotations

from collections import Counter
import unittest

from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability as availability
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability_preregistration as prereg
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_campaign as campaign
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as base


def judgment(key: str, *, bad: bool) -> dict:
    return {
        "exact_teacher_action": f"teacher-{key}" if bad else "historical",
        "historical_action": "historical",
    }


class AnchoredOosCampaignTests(unittest.TestCase):
    def test_rejects_lattice_without_frozen_per_pool_order(self) -> None:
        registration = {
            "schema": prereg.SCHEMA_TERMINAL,
            "verdict": prereg.READY,
            "passed": True,
            "fresh_pair_availability_authorized": True,
            "fresh_target_reconstruction_authorized": False,
            "oos_campaign_authorized": False,
            "protocol": {
                "fresh_campaign": {
                    "games_exact": prereg.SOURCE_GAMES,
                    "openings_per_pool": prereg.OPENINGS_PER_POOL,
                    "pool_seeds": [prereg.OOS_POOL1_SEED, prereg.OOS_POOL2_SEED],
                    "split_seed": prereg.OOS_SPLIT_SEED,
                    "target_free_before_candidate_order": True,
                },
                "fresh_pair_mining": {
                    "pair_count_exact": prereg.OOS_PAIRS,
                    "pair_count_per_pool_exact": prereg.PAIR_COUNT_PER_POOL,
                    "seed": prereg.OOS_SPLIT_SEED,
                    "stop_rule": campaign.STOP_RULE,
                    "maximum_states_per_source_game": 2,
                    "target_free_before_selection": True,
                },
            },
        }
        report = {
            "schema": availability.SCHEMA_TERMINAL,
            "verdict": availability.READY,
            "passed": True,
            "oos_target_reconstruction_authorized": True,
            "pairs_required_by_pool": campaign.PAIR_COUNT_BY_POOL,
        }
        lattice = {
            "schema": availability.SCHEMA_LATTICE,
            "pair_count_required": campaign.PAIR_COUNT,
            "pair_count_required_by_pool": campaign.PAIR_COUNT_BY_POOL,
            "selection_rule": "wrong",
            "candidate_order_fixed_before_targets": True,
            "exact_action_value_reads": 0,
        }
        with self.assertRaisesRegex(ValueError, "per-pool order drift"):
            campaign._check_availability_contract(registration, report, lattice)

    def test_accepts_exact_independent_per_pool_quotas(self) -> None:
        edges = []
        judgments = {}
        for index in range(3):
            for pool in ("pool1", "pool2"):
                left, right = f"{pool}-l{index}", f"{pool}-r{index}"
                edges.append(
                    {
                        "source_pool": pool,
                        "left_exact_state_key": left,
                        "right_exact_state_key": right,
                        "distance": index,
                    }
                )
                judgments[left] = judgment(left, bad=True)
                judgments[right] = judgment(right, bad=False)
        accepted, _used, unresolved = base._accepted(
            {"candidate_edges": edges},
            judgments,
            pair_count=4,
            pair_count_by_pool={"pool1": 2, "pool2": 2},
        )
        self.assertEqual(Counter(row["source_pool"] for row in accepted), Counter({"pool1": 2, "pool2": 2}))
        self.assertEqual(unresolved, [])

    def test_unknown_prefix_blocks_only_its_own_pool(self) -> None:
        edges = []
        judgments = {}
        for index in range(2):
            for pool in ("pool1", "pool2"):
                left, right = f"{pool}-l{index}", f"{pool}-r{index}"
                edges.append(
                    {
                        "source_pool": pool,
                        "left_exact_state_key": left,
                        "right_exact_state_key": right,
                        "distance": index,
                    }
                )
                if pool == "pool2":
                    judgments[left] = judgment(left, bad=True)
                    judgments[right] = judgment(right, bad=False)
        accepted, _used, unresolved = base._accepted(
            {"candidate_edges": edges},
            judgments,
            pair_count=4,
            pair_count_by_pool={"pool1": 2, "pool2": 2},
        )
        self.assertEqual(Counter(row["source_pool"] for row in accepted), Counter({"pool2": 2}))
        self.assertEqual(set(unresolved), {"pool1-l0", "pool1-r0", "pool1-l1", "pool1-r1"})

    def test_rejects_total_per_pool_quota_drift(self) -> None:
        with self.assertRaisesRegex(ValueError, "total/per-pool"):
            base._accepted(
                {"candidate_edges": []}, {},
                pair_count=3,
                pair_count_by_pool={"pool1": 2, "pool2": 2},
            )


if __name__ == "__main__":
    unittest.main()
