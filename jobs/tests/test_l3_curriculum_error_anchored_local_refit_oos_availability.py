from __future__ import annotations

import hashlib
from unittest import mock
import unittest

from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability as availability
from jobs.tools import l3_curriculum_error_anchored_local_refit_oos_availability_preregistration as prereg
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as base
from jobs.tools import l3_curriculum_search_error_atlas as profiles


def registration() -> dict:
    return {
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
                "stop_rule": "first_300_valid_pairs_per_pool_in_frozen_pre_target_order",
                "maximum_states_per_source_game": base.MAX_STATES_PER_GAME,
                "target_free_before_selection": True,
            },
        },
    }


class AnchoredOosAvailabilityTests(unittest.TestCase):
    def test_rejects_per_pool_or_seed_drift(self) -> None:
        row = registration()
        row["protocol"]["fresh_pair_mining"]["pair_count_per_pool_exact"] = 299
        with self.assertRaisesRegex(ValueError, "protocol drift"):
            availability._validate_preregistration(row)
        row = registration()
        row["protocol"]["fresh_campaign"]["pool_seeds"][1] += 1
        with self.assertRaisesRegex(ValueError, "protocol drift"):
            availability._validate_preregistration(row)

    @mock.patch.object(base.trace, "_profile_values", return_value={"max_depth_score_spread_cp": 100.0})
    @mock.patch.object(
        base,
        "_piece",
        return_value={"phase": "midgame", "piece_count": 24, "king_count": 2, "stm_material_balance": 0},
    )
    def test_passes_only_with_two_pool_target_free_capacity(
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
            "schema": availability.SCHEMA_SELECTION,
            "target_free": True,
            "source_games": prereg.SOURCE_GAMES,
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
        report, lattice = availability.audit(
            registration(), selection, shards,
            {"passed": True, "projected_minutes": 100.0},
            {"passed": True, "total_pairs": 138, "projected_minutes": 30.0},
        )
        self.assertEqual(report["verdict"], availability.READY)
        self.assertTrue(report["oos_target_reconstruction_authorized"])
        self.assertEqual(report["pairs_required_by_pool"], {"pool1": 300, "pool2": 300})
        self.assertEqual(lattice["schema"], availability.SCHEMA_LATTICE)
        self.assertEqual(lattice["pair_count_required_by_pool"], {"pool1": 300, "pool2": 300})
        self.assertEqual(report["new_targets"], 0)


if __name__ == "__main__":
    unittest.main()
