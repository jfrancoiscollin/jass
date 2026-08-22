#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from jobs.tools import l3_curriculum_error_learning as learning
from jobs.tools import l3_curriculum_search_error_atlas as atlas


FEN = "W:W31-50:B1-20"


def source_row(ordinal: int, opening: str, split: str, *, error: bool) -> dict:
    return {
        "ordinal": ordinal,
        "game_uid": f"g-{ordinal}",
        "opening_id": opening,
        "split": split,
        "outcome": "loss" if error else "win",
        "ply": 10,
        "fen": FEN,
        "exact_state_key": f"s-{ordinal}",
        "actual_move": "31-26",
        "actual_apply": "31-26",
        "stratum": "opening|no_kings|quiet",
        "move_differs": error,
        "regret_cp": 100 if error else 0,
    }


def profile_row(source: dict, role: str, profile_ordinal: int) -> dict:
    trace_depths = {
        str(depth): {
            "best_action": "31-26",
            "score": 0,
            "nodes": depth * 10,
            "moves": [{"action": "31-26", "score": 0}],
            "root_margin_proxy_cp": 30,
        }
        for depth in range(1, 11)
    }
    return {
        "role": role,
        "profile_ordinal": profile_ordinal,
        "source": source,
        "piece_features": atlas._piece_features(FEN),
        "legal_moves": 9,
        "trace": {
            "original": {"depths": trace_depths},
            "exact_image": {"depths": trace_depths},
        },
        "matching_features": {
            "original_best_action": "31-26",
            "mapped_image_best_action": "31-26",
            "exact_image_best_agreement": True,
            "root_margin_proxy_cp": 30,
            "depth_flip_count_8_10": 0,
            "score_volatility_8_10_cp": 0,
        },
    }


def controller_root(*, error: bool, risk: int) -> dict:
    regrets = {8: 100 if error else 0, 9: 100 if error else 0, 10: 100 if error else 0,
               11: 0 if error else 0, 12: 0 if error else 0}
    nodes = {8: 40, 9: 50, 10: 100, 11: 150, 12: 200}
    arms = {}
    for name in ("Q00", *atlas.ARM_OVERRIDES):
        arms[name] = {
            "teacher_in_paired_choices": name == "NO_LMR",
            "exact_image_agreement": True,
            "mean_nodes": 100,
        }
    return {
        "historical_regret_cp": 100 if error else 0,
        "exact_symmetrised_judge": True,
        "exact_image_child_commutations": 2,
        "risk_features": {
            "original": {"risk_score": risk},
            "exact_image": {"risk_score": risk},
            "runtime_uses_exact_image": False,
        },
        "policy_depths": {
            str(depth): {
                "original_regret_cp": regret,
                "exact_image_regret_cp": regret,
                "mean_regret_cp": regret,
                "original_nodes": nodes[depth],
                "exact_image_nodes": nodes[depth],
                "mean_exact_image_nodes": nodes[depth],
            }
            for depth, regret in regrets.items()
        },
        "ablation_arms": arms,
    }


def budget_cost_row(*, risk: int, split: str) -> dict:
    nodes = {8: 40, 9: 50, 10: 100, 11: 150, 12: 200}
    return {
        "split": split,
        "risk_features": {
            "original": {"risk_score": risk},
            "exact_image": {"risk_score": risk},
        },
        "policy_depths": {
            str(depth): {
                "original_nodes": value,
                "exact_image_nodes": value,
                "mean_exact_image_nodes": value,
            }
            for depth, value in nodes.items()
        },
    }


class CurriculumSearchErrorAtlasTests(unittest.TestCase):
    def test_job_template_and_root_cost_trace_are_preregistered(self) -> None:
        root = Path(__file__).resolve().parents[2]
        template = (root / "jobs/templates/l3-curriculum-search-error-atlas-v1.sh").read_text()
        search = (root / "src/search.cpp").read_text()
        for token in (
            "SOURCE_ERRORS=388",
            "--candidates-per-error 16",
            "--budget-rows-per-split 1024",
            "MAX_PROFILE_MINUTES=240",
            "MAX_ATLAS_MINUTES=480",
            "--bootstrap-samples \"$BOOTSTRAP\"",
            "NO_SELFPLAY",
            "NO_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
        ):
            self.assertIn(token, template)
        self.assertIn('<< " nodes=" << s.nodes', search)
        self.assertNotIn("--selfplay", template)

    def test_exact_image_move_is_an_involution_with_capture_identity(self) -> None:
        source = "31x22 captures=27,28"
        image = atlas._mapped_image_action(source)
        self.assertEqual(image, "20x29 captures=23,24")
        self.assertEqual(atlas._mapped_image_action(image), source)

    def test_prepare_uses_decision_controls_but_excludes_error_openings(self) -> None:
        rows = [
            source_row(0, "e-d", "discovery", error=True),
            source_row(1, "c-d", "discovery", error=False),
            source_row(2, "e-c", "confirm", error=True),
            source_row(3, "c-c", "confirm", error=False),
        ]
        selection = {
            "schema": learning.SCHEMA_SELECTION,
            "decisions": len(rows),
            "rows": [{"ordinal": index} for index in range(len(rows))],
        }
        digest = hashlib.sha256(learning._canonical(selection)).hexdigest()
        shard = {
            "schema": learning.SCHEMA_SHARD,
            "selection_sha256": digest,
            "shard": 0,
            "nshards": 1,
            "rows": rows,
        }
        payload = atlas.prepare_profile_selection(
            selection, [shard], min_regret_cp=50,
            max_control_regret_cp=10, candidates_per_error=4,
        )
        self.assertEqual(payload["error_openings"], 2)
        self.assertEqual(payload["control_candidate_decisions"], 2)
        self.assertTrue(payload["decision_level_controls"])
        self.assertEqual(
            {row["source"]["opening_id"] for row in payload["rows"] if row["role"] == "control_candidate"},
            {"c-d", "c-c"},
        )
        for candidates in payload["candidate_map"].values():
            openings = {
                rows[ordinal]["opening_id"]
                for ordinal in candidates
            }
            self.assertEqual(len(openings), len(candidates))

    def test_fine_matching_is_opening_disjoint_and_without_replacement(self) -> None:
        errors = [
            profile_row(source_row(0, "e-d", "discovery", error=True), "error", 0),
            profile_row(source_row(1, "e-c", "confirm", error=True), "error", 1),
        ]
        controls = [
            profile_row(source_row(2, "c-d", "discovery", error=False), "control_candidate", 2),
            profile_row(source_row(3, "c-c", "confirm", error=False), "control_candidate", 3),
        ]
        selection = {
            "schema": atlas.SCHEMA_SELECTION,
            "rows": [
                {"role": row["role"], "profile_ordinal": row["profile_ordinal"], "source": row["source"]}
                for row in errors + controls
            ],
            "candidate_map": {"0": [2], "1": [3]},
        }
        digest = hashlib.sha256(atlas._canonical(selection)).hexdigest()
        shard = {
            "schema": atlas.SCHEMA_PROFILE_SHARD,
            "selection_sha256": digest,
            "shard": 0,
            "nshards": 1,
            "max_rows": 0,
            "rows": errors + controls,
        }
        result = atlas.match_profiles(selection, [shard])
        self.assertTrue(result["matching_passed"])
        self.assertEqual(result["matched_pairs"], 2)
        self.assertEqual(result["opening_overlap"], 0)
        self.assertTrue(result["maximum_cardinality_matching"])

    def test_controller_is_selected_at_equal_mean_node_budget(self) -> None:
        errors = [controller_root(error=True, risk=3) for _ in range(8)]
        controls = [controller_root(error=False, risk=0) for _ in range(8)]
        budget = [budget_cost_row(risk=3, split="discovery") for _ in range(8)] + [
            budget_cost_row(risk=0, split="discovery") for _ in range(8)
        ]
        policy = atlas.select_controller(errors, controls, budget)
        self.assertIsNotNone(policy)
        simulation = atlas._simulate_costs(budget, policy)
        self.assertAlmostEqual(simulation["node_budget_ratio"], 1.0)
        self.assertGreater(atlas._simulate(errors, policy)["mean_regret_reduction_cp"], 0)

    def test_terminal_report_requires_sealed_confirmation(self) -> None:
        pair_rows = []
        for split in ("discovery", "confirm"):
            for index in range(40):
                pair_rows.append(
                    {
                        "pair_id": len(pair_rows),
                        "split": split,
                        "error": controller_root(error=True, risk=3),
                        "control": controller_root(error=False, risk=0),
                    }
                )
        pairs = {
            "schema": atlas.SCHEMA_PAIRS,
            "error_openings": 80,
            "matched_pairs": 80,
            "matched_fraction": 1.0,
            "pairs": [{"pair_id": row["pair_id"]} for row in pair_rows],
            "budget_calibration": [
                budget_cost_row(risk=risk, split=split)
                for split in ("discovery", "confirm")
                for risk in (3, 0)
                for _ in range(256)
            ],
        }
        digest = hashlib.sha256(atlas._canonical(pairs)).hexdigest()
        shard = {
            "schema": atlas.SCHEMA_ATLAS_SHARD,
            "pairs_sha256": digest,
            "champion_sha256": "a" * 64,
            "jass_sha256": "b" * 64,
            "search_params_sha256": "c" * 64,
            "shard": 0,
            "nshards": 1,
            "max_pairs": 0,
            "rows": pair_rows,
        }
        report = atlas.aggregate_atlas(
            pairs, [shard], bootstrap_samples=2000, bootstrap_seed=17
        )
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["verdict"],
            "JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_SCREEN_PASSED",
        )
        self.assertEqual(report["search_ablation"]["localized_mechanism"], "NO_LMR")
        self.assertTrue(report["weights_bit_identical"])
        self.assertFalse(report["controller_runtime_uses_exact_image"])


if __name__ == "__main__":
    unittest.main()
