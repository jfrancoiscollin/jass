from __future__ import annotations

import copy
from unittest import mock
import unittest

from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirm
from jobs.tools import l3_curriculum_error_endgame_abstention_preregistration as prereg


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
                "maximum_states_per_source_game": 2,
                "target_free_before_candidate_order": True,
            },
            "fresh_confirmation": {
                "bootstrap_samples": prereg.BOOTSTRAP_SAMPLES,
                "bootstrap_seed": prereg.BOOTSTRAP_SEED,
                "sham_replicates": prereg.SHAM_REPLICATES,
                "sham_seed": prereg.SHAM_SEED,
                "minimum_error_interventions": prereg.MIN_ERROR_INTERVENTIONS,
                "minimum_control_interventions": prereg.MIN_CONTROL_INTERVENTIONS,
                "minimum_total_interventions": prereg.MIN_TOTAL_INTERVENTIONS,
                "minimum_error_interventions_per_pool": prereg.MIN_ERROR_INTERVENTIONS_PER_POOL,
                "minimum_control_interventions_per_pool": prereg.MIN_CONTROL_INTERVENTIONS_PER_POOL,
                "all_gates_required_jointly": True,
                "endgame_interventions_exactly": 0,
                "endgame_decisions_bit_identical_to_CURRICULUM_anchor": True,
                "non_endgame_decisions_bit_identical_to_frozen_1517_residual": True,
            },
        },
    }


def decision(intervention: bool) -> dict:
    return {
        "eligible": True,
        "intervention": intervention,
        "improvement_cp": 125.0 if intervention else 0.0,
        "predicted_advantage_cp": 20.0 if intervention else None,
        "realized_gain_cp": 125.0 if intervention else None,
        "anchor_symmetry": False,
        "aligned_symmetry": intervention,
        "outside_gate_bit_identical": True,
        "action": "31-26" if intervention else None,
    }


class EndgameAbstentionConfirmationTests(unittest.TestCase):
    def test_preregistration_freezes_all_confirmatory_counts(self) -> None:
        selected = confirm._check_preregistration(registration())
        self.assertEqual(selected["alpha"], 300.0)
        self.assertEqual(selected["phase_rule"]["abstain_exact_value"], "endgame")
        row = registration()
        row["protocol"]["fresh_confirmation"]["minimum_error_interventions"] = 59
        with self.assertRaisesRegex(ValueError, "minimum_error_interventions"):
            confirm._check_preregistration(row)

    @mock.patch.object(confirm, "_phase", side_effect=["endgame", "midgame"])
    def test_endgame_abstains_and_non_endgame_is_bit_identical(self, _phase: mock.Mock) -> None:
        rows = [{
            "pair_id": 0,
            "source_pool": "pool1",
            "error": {"profile": {"source": {}}},
            "control": {"profile": {"source": {}}},
        }]
        base_decisions = [{"pair_id": 0, "error": decision(True), "control": decision(True)}]
        output, proof = confirm._apply_endgame_abstention(rows, base_decisions)
        self.assertFalse(output[0]["error"]["intervention"])
        self.assertEqual(output[0]["error"]["improvement_cp"], 0.0)
        self.assertTrue(output[0]["error"]["would_intervene_without_endgame_abstention"])
        for key, value in base_decisions[0]["control"].items():
            self.assertEqual(output[0]["control"][key], value)
        self.assertEqual(proof["endgame_interventions"], 0)
        self.assertTrue(proof["endgame_decisions_bit_identical_to_anchor"])
        self.assertTrue(proof["non_endgame_decisions_bit_identical_to_frozen_residual"])

    @mock.patch.object(confirm.base, "prepare_with_contract", return_value=({}, []))
    def test_prepare_uses_600_pair_frozen_contract(self, prepare: mock.Mock) -> None:
        confirm.prepare({}, {}, {}, {}, {}, [])
        self.assertEqual(prepare.call_args.kwargs["pair_count"], 600)
        self.assertEqual(prepare.call_args.kwargs["mining_seed"], prereg.MINING_SEED)
        self.assertEqual(
            prepare.call_args.kwargs["lattice_schema"],
            "jass.l3_curriculum_error_endgame_abstention_lattice.v1",
        )


if __name__ == "__main__":
    unittest.main()
