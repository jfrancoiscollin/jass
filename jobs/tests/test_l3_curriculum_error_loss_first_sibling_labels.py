import copy
import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_error_loss_first_sibling_labels as labels


class FakeMove:
    def __init__(self, text="31-27"):
        self.text = text

    def jass_apply_str(self):
        return self.text


def source_summary():
    return {
        "schema": labels.SOURCE_SCHEMA,
        "verdict": labels.SOURCE_VERDICT,
        "passed": True,
        "deep_target_computations": 0,
        "new_selfplay_games": 1536,
        "next_stage": "loss_first_all_legal_sibling_labeling",
        "preregistration": {
            "job": "cpx62-1542-l3-curriculum-error-loss-first-sibling-rank-preregistration-v1",
            "attempt": "attempt",
            "code_sha": "a" * 40,
        },
    }


def prereg():
    return {
        "verdict": labels.PREREG_VERDICT,
        "passed": True,
        "deep_sibling_labeling_authorized_after_source_audit": True,
        "anchored_local_refit_authorized": False,
        "source_campaign": {"total_games": 1536, "source_stage_has_no_deep_targets": True},
    }


def selection():
    rows = []
    for ordinal, pool in enumerate((1, 2)):
        rows.append({
            "ordinal": ordinal,
            "source_file": f"/run/games-pool{pool}/game-0.json",
            "game_uid": f"game-{pool}",
            "opening_id": f"opening-{pool}",
            "outcome": "loss" if pool == 1 else "win",
            "ply": ordinal,
            "fen": "W:W31,32:B1,2",
            "exact_state_key": f"state-{pool}",
            "actual_move": "31-27",
        })
    return {
        "schema": learning.SCHEMA_SELECTION,
        "decisions": len(rows),
        "rows": rows,
    }


def transitions(source):
    return {
        "schema": learning.SCHEMA_TRANSITIONS,
        "selection_sha256": labels._digest(source),
        "transitions": [
            {"ordinal": index, "next_fen": "B:W27,32:B1,2"}
            for index in range(len(source["rows"]))
        ],
    }


class LossFirstSiblingLabelsTests(unittest.TestCase):
    def test_candidate_rows_are_outcome_blind(self):
        original = selection()
        permuted = copy.deepcopy(original)
        for row in permuted["rows"]:
            row["outcome"] = "draw"
        with (
            mock.patch.object(labels, "MIN_SELECTED_PER_POOL", 1),
            mock.patch.object(
                learning, "_dump_legal_lines", return_value=["31>27 32>28"] * 2
            ),
            mock.patch.object(
                learning, "_resolve_historical_transition", return_value=FakeMove()
            ),
        ):
            left = labels.build_candidates(
                original, transitions(original), source_summary(), prereg(),
                jass="unused", seed=43,
            )
            right = labels.build_candidates(
                permuted, transitions(permuted), source_summary(), prereg(),
                jass="unused", seed=43,
            )
        self.assertEqual(left["candidates"], right["candidates"])
        self.assertNotIn("outcome", left["candidates"][0])
        self.assertTrue(left["canonical_unique"])

    def test_profile_selection_is_one_state_per_opening(self):
        candidates = {
            "schema": labels.SCHEMA_CANDIDATES,
            "candidate_count": 4,
            "candidates": [],
        }
        rows = []
        for ordinal, (pool, opening, score) in enumerate(
            ((1, "a", 1.0), (1, "a", 5.0), (2, "b", 2.0), (2, "b", 3.0))
        ):
            rows.append({
                "candidate_key": f"k{ordinal}", "source_ordinal": ordinal,
                "pool": pool, "opening_id": opening, "game_uid": f"g{ordinal}",
                "exact_state_key": f"s{ordinal}", "fen": "W:W31:B1",
                "historical_action": "31-27", "legal_actions": ["31-27"],
                "structural": {}, "shallow_trace": {}, "instability": {"score": score},
            })
        shards = []
        for shard in range(16):
            shards.append({
                "schema": labels.SCHEMA_PROFILE_SHARD, "shard": shard,
                "candidates_sha256": labels._digest(candidates),
                "champion_sha256": "c", "jass_sha256": "j",
                "search_params_sha256": "q",
                "rows": rows if shard == 0 else [],
            })
        with mock.patch.object(labels, "MIN_SELECTED_PER_POOL", 1):
            result = labels.combine_profiles(candidates, shards, seed=43)
        self.assertEqual(result["selected"], 2)
        self.assertEqual([row["candidate_key"] for row in result["rows"]], ["k1", "k3"])
        self.assertTrue(result["one_state_per_opening"])

    def test_matching_is_exact_and_without_replacement(self):
        def row(pool, opening, state, label):
            return {
                "pool": pool, "opening_id": opening, "game_uid": f"g-{opening}",
                "exact_state_key": state, "label": label,
                "structural": {
                    "phase": "midgame", "kings": "kings", "tactical": "quiet",
                    "branching_bin": "b03_05",
                },
            }
        rows = [
            row(1, "e1", "se1", "error"), row(1, "c1", "sc1", "control"),
            row(2, "e2", "se2", "error"), row(2, "c2", "sc2", "control"),
        ]
        pairs = labels._match(rows, seed=44)
        self.assertEqual(len(pairs), 2)
        self.assertEqual({pair["pool"] for pair in pairs}, {1, 2})
        self.assertEqual(len({pair["control"]["exact_state_key"] for pair in pairs}), 2)

    def test_aggregate_authorizes_only_next_screen(self):
        selection_payload = {
            "schema": labels.SCHEMA_SELECTION, "selected": 4,
            "rows": [{"label_ordinal": index} for index in range(4)],
        }
        base = {
            "accepted": True, "depth_top_agreement": True,
            "wdl_ordering_agreement": True, "symmetry_ordering_agreement": True,
        }
        rows = []
        for ordinal, (pool, role) in enumerate(((1, "error"), (1, "control"), (2, "error"), (2, "control"))):
            rows.append({
                **base, "label_ordinal": ordinal, "pool": pool, "label": role,
                "opening_id": f"o{ordinal}", "game_uid": f"g{ordinal}",
                "exact_state_key": f"s{ordinal}",
                "structural": {
                    "phase": "midgame", "kings": "kings", "tactical": "quiet",
                    "branching_bin": "b03_05",
                },
            })
        shards = []
        for shard in range(16):
            shards.append({
                "schema": labels.SCHEMA_LABEL_SHARD, "shard": shard,
                "selection_sha256": labels._digest(selection_payload),
                "champion_sha256": "c", "jass_sha256": "j",
                "search_params_sha256": "q", "max_rows": 0,
                "rows": rows if shard == 0 else [],
            })
        with mock.patch.object(labels, "MIN_MATCHED_PER_POOL", 1):
            report, pairs = labels.aggregate(selection_payload, shards, match_seed=44)
        self.assertTrue(report["passed"])
        self.assertFalse(report["anchored_local_refit_authorized"])
        self.assertEqual(report["next_stage"], "loss_first_sparse_jacobian_crossfit_screen")
        self.assertEqual(len(pairs["pairs"]), 2)


if __name__ == "__main__":
    unittest.main()
