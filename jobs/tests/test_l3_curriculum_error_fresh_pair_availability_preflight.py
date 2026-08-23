from __future__ import annotations

import hashlib
import json
from unittest import mock
import unittest

from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as fresh
from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_error_residual_power_extension_preregistration as power
from jobs.tools import l3_curriculum_search_error_atlas as profiles


def preregistration() -> dict:
    return {
        "schema": power.SCHEMA,
        "verdict": power.READY,
        "passed": True,
        "fresh_pair_mining_authorized": True,
        "fresh_target_reconstruction_authorized": False,
        "protocol": {
            "fresh_pair_mining": {
                "pair_count_exact": power.FRESH_PAIRS,
                "seed": power.MINING_SEED,
                "maximum_states_per_source_game": fresh.MAX_STATES_PER_GAME,
                "target_free_before_selection": True,
            }
        },
    }


class FreshPairAvailabilityTest(unittest.TestCase):
    def test_prepare_is_loss_only_canonical_and_capped(self) -> None:
        rows = []
        for game in range(3):
            for index in range(12):
                rows.append(
                    {
                        "ordinal": len(rows),
                        "game_uid": f"g{game}",
                        "source_file": f"/tmp/games-pool{1 + game % 2}/game-{game}.json",
                        "opening_id": f"o{game}",
                        "outcome": "loss" if game < 2 else "win",
                        "ply": index,
                        "fen": f"W:W{index + 1}:B50",
                        "exact_state_key": f"s{game}-{index}",
                        "actual_move": "1-2",
                    }
                )
        source = {
            "schema": learning.SCHEMA_SELECTION,
            "games": 3,
            "decisions": len(rows),
            "rows": rows,
            "external_teacher_inputs": 0,
            "fit_count": 0,
        }
        output = fresh.prepare_profile_selection(source)
        self.assertEqual(len(output["rows"]), 12)
        self.assertEqual(output["loss_games"], 2)
        self.assertTrue(all(row["source"]["outcome"] == "loss" for row in output["rows"]))
        counts = {}
        for row in output["rows"]:
            counts[row["source"]["game_uid"]] = counts.get(row["source"]["game_uid"], 0) + 1
        self.assertEqual(set(counts.values()), {fresh.PREPROFILE_STATES_PER_GAME})

    def test_prepare_rejects_action_targets(self) -> None:
        source = {
            "schema": learning.SCHEMA_SELECTION,
            "games": 1,
            "decisions": 1,
            "rows": [{"teacher": {}}],
            "external_teacher_inputs": 0,
            "fit_count": 0,
        }
        with self.assertRaisesRegex(ValueError, "exact action targets"):
            fresh.prepare_profile_selection(source)

    @mock.patch.object(fresh.trace, "_profile_values", return_value={"max_depth_score_spread_cp": 100.0})
    @mock.patch.object(
        fresh,
        "_piece",
        return_value={"phase": "midgame", "piece_count": 24, "king_count": 2, "stm_material_balance": 0},
    )
    def test_audit_passes_with_powered_two_pool_lattice(self, _piece: mock.Mock, _values: mock.Mock) -> None:
        rows = []
        for index in range(1920):
            pool = "pool1" if index < 960 else "pool2"
            rows.append(
                {
                    "role": "fresh_target_free_candidate",
                    "profile_ordinal": index,
                    "source_pool": pool,
                    "source": {
                        "ordinal": index,
                        "opening_id": f"opening-{index}",
                        "game_uid": f"game-{index}",
                        "exact_state_key": hashlib.sha256(f"state-{index}".encode()).hexdigest(),
                        "outcome": "loss",
                        "ply": 20,
                        "fen": "W:W31,32:B1,2",
                        "actual_move": "31-26",
                    },
                    "legal_moves": 7,
                }
            )
        selection = {
            "schema": fresh.SCHEMA_SELECTION,
            "target_free": True,
            "source_games": fresh.SOURCE_GAMES,
            "rows_by_pool": {"pool1": 960, "pool2": 960},
            "rows": rows,
        }
        digest = hashlib.sha256(fresh._canonical(selection)).hexdigest()
        shards = []
        for shard in range(16):
            shards.append(
                {
                    "schema": profiles.SCHEMA_PROFILE_SHARD,
                    "selection_sha256": digest,
                    "shard": shard,
                    "nshards": 16,
                    "rows": [row for row in rows if row["profile_ordinal"] % 16 == shard],
                }
            )
        report, lattice = fresh.audit(
            preregistration(),
            selection,
            shards,
            {"passed": True, "projected_minutes": 40.0},
            {"passed": True, "total_pairs": 138, "projected_minutes": 90.0},
        )
        self.assertEqual(report["verdict"], fresh.READY)
        self.assertGreaterEqual(report["raw_pair_capacity"], 900)
        self.assertEqual(report["exact_action_value_reads"], 0)
        self.assertEqual(lattice["maximum_states_per_source_game"], 2)
        self.assertEqual(len({row["exact_state_key"] for row in lattice["candidate_states"]}), 1920)

    def test_lattice_never_pairs_same_game_or_opening(self) -> None:
        candidates = []
        for index in range(20):
            candidates.append(
                {
                    "source_pool": "pool1",
                    "game_uid": f"g{index}",
                    "opening_id": f"o{index}",
                    "exact_state_key": hashlib.sha256(f"s{index}".encode()).hexdigest(),
                    "outcome": "loss",
                    "ply": 10,
                    "actual_move": "1-2",
                    "piece_features": {"phase": "midgame", "piece_count": 24, "king_count": 0, "stm_material_balance": 0},
                    "legal_moves": 5,
                    "proxy_value_cp": 100.0,
                    "candidate_order_sha256": hashlib.sha256(f"order-{index}".encode()).hexdigest(),
                }
            )
        edges, _capacity = fresh._lattice(candidates, seed=power.MINING_SEED)
        by_state = {row["exact_state_key"]: row for row in candidates}
        for edge in edges:
            left, right = by_state[edge["left_exact_state_key"]], by_state[edge["right_exact_state_key"]]
            self.assertNotEqual(left["game_uid"], right["game_uid"])
            self.assertNotEqual(left["opening_id"], right["opening_id"])


if __name__ == "__main__":
    unittest.main()
