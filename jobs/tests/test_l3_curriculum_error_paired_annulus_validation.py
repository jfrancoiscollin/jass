#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

from jobs.tools import l3_curriculum_error_paired_annulus_validation as target


def _model() -> dict:
    return {
        "mean": [0.0],
        "scale": [1.0],
        "coef": [75.0],
        "correction_cap_cp": 75.0,
    }


def _paired(*, margin: float) -> tuple[dict, dict, dict, dict]:
    scores = {"a": 100.0, "b": 100.0 - margin}
    features = {"a": np.asarray([-1.0]), "b": np.asarray([1.0])}
    return features, scores, dict(scores), dict(scores)


class PairedAnnulusValidationTests(unittest.TestCase):
    def test_direct_script_execution_resolves_local_imports(self):
        root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [sys.executable, str(root / "jobs" / "tools" / "l3_curriculum_error_paired_annulus_validation.py"), "--help"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @mock.patch.object(target, "_paired_features", return_value=_paired(margin=60.0))
    @mock.patch.object(target.ranker, "_true_values", return_value={"a": 0.0, "b": 100.0})
    def test_annulus_intervention_is_symmetric_and_improves(self, _values, _features):
        decision = target._decision({"profile": {}, "judged": {}}, _model())
        self.assertTrue(decision["eligible"])
        self.assertTrue(decision["residual_intervention"])
        self.assertEqual(decision["aligned_action_original"], "b")
        self.assertEqual(decision["aligned_action_image"], "b")
        self.assertTrue(decision["aligned_symmetry"])
        self.assertGreater(decision["realized_residual_gain_cp"], 0.0)

    @mock.patch.object(target, "_paired_features", return_value=_paired(margin=30.0))
    @mock.patch.object(target.ranker, "_true_values", return_value={"a": 0.0, "b": 100.0})
    def test_outside_annulus_is_bit_identical(self, _values, _features):
        decision = target._decision({"profile": {}, "judged": {}}, _model())
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["residual_intervention"])
        self.assertEqual(decision["aligned_action_original"], decision["anchor_original"])
        self.assertEqual(decision["aligned_action_image"], decision["anchor_image"])
        self.assertTrue(decision["outside_annulus_bit_identical"])

    def test_calibration_reports_bias_and_positive_rate(self):
        result = target._calibration(
            [
                {"residual_intervention": True, "predicted_advantage_cp": 30.0, "realized_residual_gain_cp": 40.0},
                {"residual_intervention": True, "predicted_advantage_cp": 50.0, "realized_residual_gain_cp": -10.0},
            ]
        )
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["positive_realization_rate"], 0.5)
        self.assertAlmostEqual(result["mean_bias_realized_minus_predicted_cp"], -25.0)

    def test_source_id_audit_covers_both_paired_roles(self):
        rows = [
            {
                "error": {"profile": {"source": {"game_uid": "g1"}}},
                "control": {"profile": {"source": {"game_uid": "g2"}}},
            }
        ]
        self.assertEqual(target._source_ids(rows, "game_uid"), {"g1", "g2"})


if __name__ == "__main__":
    unittest.main()
