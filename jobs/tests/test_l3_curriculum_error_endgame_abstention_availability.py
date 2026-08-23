from __future__ import annotations

import hashlib
import copy
from unittest import mock
import unittest

from jobs.tools import l3_curriculum_error_endgame_abstention_availability as endgame
from jobs.tools import l3_curriculum_error_endgame_abstention_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as base
from jobs.tools import l3_curriculum_search_error_atlas as profiles


def registration() -> dict:
    return {
        "schema": "jass.curriculum_error_endgame_abstention_preregistration_terminal.v1",
        "verdict": prereg.READY,
        "passed": True,
        "fresh_pair_availability_authorized": True,
        "fresh_target_reconstruction_authorized": False,
        "frozen_hypothesis": copy.deepcopy(prereg.FROZEN_HYPOTHESIS),
        "protocol": {
            "fresh_campaign": {
                "games_exact": prereg.SOURCE_GAMES,
                "openings_per_pool": prereg.OPENINGS_PER_POOL,
                "pool_seeds": list(prereg.POOL_SEEDS),
                "split_seed": prereg.SPLIT_SEED,
            },
            "fresh_pair_mining": {
                "pair_count_exact": prereg.FRESH_PAIRS,
                "seed": prereg.MINING_SEED,
                "maximum_states_per_source_game": base.MAX_STATES_PER_GAME,
                "target_free_before_candidate_order": True,
            },
        },
    }


class EndgameAbstentionAvailabilityTests(unittest.TestCase):
    def test_rejects_phase_or_seed_drift(self) -> None:
        row = registration()
        row["protocol"]["fresh_campaign"]["pool_seeds"][0] += 1
        with self.assertRaisesRegex(ValueError, "protocol drift"):
            endgame._validate_preregistration(row)
        row = registration()
        row["frozen_hypothesis"]["phase_rule"]["abstain_exact_value"] = "midgame"
        with self.assertRaisesRegex(ValueError, "protocol drift"):
            endgame._validate_preregistration(row)

    @mock.patch.object(base.trace, "_profile_values", return_value={"max_depth_score_spread_cp": 100.0})
    @mock.patch.object(
        base,
        "_piece",
        return_value={"phase": "midgame", "piece_count": 24, "king_count": 2, "stm_material_balance": 0},
    )
    def test_passes_only_with_doubled_two_pool_capacity(
        self, _piece: mock.Mock, _values: mock.Mock
    ) -> None:
        rows = []
        for index in range(3840):
            pool = "pool1" if index < 1920 else "pool2"
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
            "schema": endgame.SCHEMA_SELECTION,
            "target_free": True,
            "source_games": endgame.SOURCE_GAMES,
            "rows_by_pool": {"pool1": 1920, "pool2": 1920},
            "rows": rows,
        }
        digest = hashlib.sha256(base._canonical(selection)).hexdigest()
        shards = [
            {
                "schema": profiles.SCHEMA_PROFILE_SHARD,
                "selection_sha256": digest,
                "shard": shard,
                "nshards": 16,
                "rows": [row for row in rows if row["profile_ordinal"] % 16 == shard],
            }
            for shard in range(16)
        ]
        report, lattice = endgame.audit(
            registration(),
            selection,
            shards,
            {"passed": True, "projected_minutes": 100.0},
            {"passed": True, "total_pairs": 138, "projected_minutes": 30.0},
        )
        self.assertEqual(report["verdict"], endgame.READY)
        self.assertGreaterEqual(report["raw_pair_capacity"], endgame.MIN_RAW_PAIR_CAPACITY)
        self.assertTrue(all(value >= 720 for value in report["raw_pair_capacity_by_pool"].values()))
        self.assertEqual(report["fresh_pair_count_required"], 600)
        self.assertEqual(report["new_selfplay_games"], 15360)
        self.assertEqual(lattice["pair_count_required"], 600)


if __name__ == "__main__":
    unittest.main()
