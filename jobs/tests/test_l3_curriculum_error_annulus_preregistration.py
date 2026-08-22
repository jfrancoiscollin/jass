#!/usr/bin/env python3
from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import sys
import unittest

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_action_ranker_oof_autopsy as autopsy
from jobs.tools import l3_curriculum_error_annulus_preregistration as target


def _candidate(alpha: float, threshold: float, margin: float, paired: float) -> dict:
    return {
        "alpha": alpha,
        "advantage_threshold_cp": threshold,
        "margin_band_cp": margin,
        "oof_passed": False,
        "oof_gates": {},
        "selection_score": paired,
        "oof": {
            "paired_error_minus_control": {"mean": paired},
            "error_changed_pairs": 20,
        },
    }


def _inputs() -> tuple[dict, dict]:
    values = {
        (10.0, 25.0, 50.0): -70.0,
        (10.0, 25.0, 100.0): 3.0,
        (10.0, 25.0, 200.0): 3.0,
        (100.0, 25.0, 50.0): -65.0,
        (100.0, 25.0, 100.0): 8.0,
        (100.0, 25.0, 200.0): 8.0,
        (100.0, 50.0, 100.0): 2.5,
    }
    candidates = [
        _candidate(alpha, threshold, margin, values.get((alpha, threshold, margin), -100.0))
        for alpha in ranker.RIDGE_ALPHAS
        for threshold in ranker.ADVANTAGE_THRESHOLDS_CP
        for margin in ranker.MARGIN_BANDS_CP
    ]
    report = {
        "schema": ranker.SCHEMA,
        "verdict": autopsy.EXPECTED_NEGATIVE,
        "passed": False,
        "selected_candidate": None,
        "sham": None,
        "inner_validation": None,
        "inner_validation_gates": {},
        "outer_confirm": None,
        "outer_confirm_gates": {},
        "outer_confirm_pairs_read": 0,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "support": {"discovery": 134, "inner_fit": 103, "inner_validation": 31, "outer_confirm": None},
        "inner_split": {"manifest_sha256": "split"},
        "candidates": candidates,
    }
    readout = {
        "schema": autopsy.SCHEMA,
        "verdict": autopsy.VERDICT,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "positive_paired_mean_candidate_count": 5,
        "classification": {
            "any_positive_candidate_changed_enough_errors": True,
            "any_positive_candidate_preserved_controls": True,
            "any_positive_candidate_passed_paired_probability_gate": False,
            "any_positive_candidate_preserved_symmetry": False,
        },
        "gate_failure_histogram": {
            "candidate_symmetry_ge_0_70": 27,
            "candidate_symmetry_not_worse": 27,
            "paired_probability_positive_ge_0_90": 27,
        },
        "validation_decision_payload_reads": 0,
        "outer_confirm_decision_payload_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    return report, readout


class AnnulusPreregistrationTests(unittest.TestCase):
    def test_direct_script_execution_resolves_local_imports(self):
        root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "jobs" / "tools" / "l3_curriculum_error_annulus_preregistration.py"),
                "--help",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_replicated_annulus_interaction_preregisters_one_fixed_architecture(self):
        report, readout = _inputs()
        result = target.analyze(report, readout)
        self.assertTrue(result["passed"])
        self.assertEqual(result["verdict"], target.READY)
        self.assertEqual(result["architectures_considered"], 1)
        self.assertEqual(result["fixed_architecture"]["alpha"], 100.0)
        self.assertEqual(result["fixed_architecture"]["baseline_d9_margin_lower_open_cp"], 50.0)
        self.assertEqual(result["fixed_architecture"]["baseline_d9_margin_upper_closed_cp"], 100.0)
        self.assertIn("equivariant_by_construction", result["fixed_architecture"]["symmetry"])
        self.assertEqual(result["validation_decision_payload_reads"], 0)
        self.assertEqual(result["outer_confirm_decision_payload_reads"], 0)

    def test_missing_replication_closes_without_architecture(self):
        report, readout = _inputs()
        broken = copy.deepcopy(report)
        for row in broken["candidates"]:
            if row["alpha"] == 10.0 and row["advantage_threshold_cp"] == 25.0 and row["margin_band_cp"] == 100.0:
                row["oof"]["paired_error_minus_control"]["mean"] = -1.0
        result = target.analyze(broken, readout)
        self.assertFalse(result["passed"])
        self.assertIsNone(result["fixed_architecture"])
        self.assertIn("alpha_10_upper_band_positive", result["failed_gates"])

    def test_any_sealed_payload_read_fails_closed(self):
        report, readout = _inputs()
        readout["outer_confirm_decision_payload_reads"] = 1
        with self.assertRaisesRegex(ValueError, "sealed readout counter drift"):
            target.analyze(report, readout)


if __name__ == "__main__":
    unittest.main()
