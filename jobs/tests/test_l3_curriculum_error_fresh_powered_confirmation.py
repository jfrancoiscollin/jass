import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh


def judgment(state, disagreement):
    return {
        "source": {"exact_state_key": state},
        "historical_action": "31>26",
        "exact_teacher_action": "32>27" if disagreement else "31>26",
    }


def profile(state):
    return {
        "source": {
            "exact_state_key": state,
            "actual_apply": "31>26",
            "opening_id": f"opening-{state}",
            "game_uid": f"game-{state}",
        }
    }


class FreshPoweredConfirmationTests(unittest.TestCase):
    def test_unknown_prefix_blocks_later_acceptance(self):
        lattice = {
            "candidate_edges": [
                {"left_exact_state_key": "a", "right_exact_state_key": "b",
                 "source_pool": "pool1", "distance": 1},
                {"left_exact_state_key": "c", "right_exact_state_key": "d",
                 "source_pool": "pool2", "distance": 2},
            ]
        }
        accepted, _used, unresolved = fresh._accepted(
            lattice, {"c": judgment("c", True), "d": judgment("d", False)}
        )
        self.assertEqual(accepted, [])
        self.assertEqual(unresolved, ["a", "b"])
        accepted, _used, _unresolved = fresh._accepted(
            lattice,
            {
                "a": judgment("a", False), "b": judgment("b", False),
                "c": judgment("c", True), "d": judgment("d", False),
            },
        )
        self.assertEqual([row["edge_index"] for row in accepted], [1])

    def test_plan_requests_only_unjudged_states(self):
        lattice = {
            "candidate_edges": [
                {"left_exact_state_key": "a", "right_exact_state_key": "b",
                 "source_pool": "pool1", "distance": 1},
            ]
        }
        catalog = {
            "schema": fresh.SCHEMA_CATALOG,
            "lattice_sha256": fresh._digest(lattice),
            "catalog": {"a": profile("a"), "b": profile("b")},
        }
        plan, batch = fresh.plan_batch(lattice, catalog, None, max_states=2)
        self.assertEqual(plan["status"], "needs_targets")
        self.assertEqual(batch["target_state_keys"], ["a", "b"])
        self.assertEqual(batch["matched_pairs"], 1)

    def test_finalize_repackages_first_valid_pairs(self):
        lattice = {
            "candidate_edges": [
                {"left_exact_state_key": "a", "right_exact_state_key": "b",
                 "source_pool": "pool1", "distance": 1},
                {"left_exact_state_key": "c", "right_exact_state_key": "d",
                 "source_pool": "pool2", "distance": 2},
            ]
        }
        catalog = {
            "schema": fresh.SCHEMA_CATALOG,
            "lattice_sha256": fresh._digest(lattice),
            "catalog": {key: profile(key) for key in "abcd"},
        }
        identities = {
            "champion_sha256": "a" * 64, "jass_sha256": "b" * 64,
            "search_params_sha256": "c" * 64, "search_arms": {},
            "judge_depth": 12,
        }
        cache = {
            "schema": fresh.SCHEMA_CACHE,
            "catalog_sha256": fresh._digest(catalog),
            "identities": identities,
            "judgments": {
                "a": judgment("a", True), "b": judgment("b", False),
                "c": judgment("c", False), "d": judgment("d", True),
            },
            "batch_receipts": [],
        }
        with mock.patch.object(fresh, "FRESH_PAIRS", 2):
            pairs, shards = fresh.finalize_pairs_and_shards(lattice, catalog, cache)
        self.assertEqual(pairs["matched_pairs"], 2)
        self.assertEqual(pairs["pairs_by_pool"], {"pool1": 1, "pool2": 1})
        self.assertEqual(pairs["pairs"][0]["error"]["source"]["exact_state_key"], "a")
        self.assertEqual(sum(len(shard["rows"]) for shard in shards), 2)
        self.assertTrue(all(shard["repacked_from_authenticated_batches"] for shard in shards))


if __name__ == "__main__":
    unittest.main()
