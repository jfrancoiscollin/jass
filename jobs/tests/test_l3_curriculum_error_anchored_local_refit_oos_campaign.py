from __future__ import annotations

from collections import Counter
import unittest

from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as base


def judgment(key: str, *, bad: bool) -> dict:
    return {
        "exact_teacher_action": f"teacher-{key}" if bad else "historical",
        "historical_action": "historical",
    }


class AnchoredOosCampaignTests(unittest.TestCase):
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
