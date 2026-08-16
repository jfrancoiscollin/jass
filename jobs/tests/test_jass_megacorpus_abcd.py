import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.jass_megacorpus_static_readout import (
    cluster_bootstrap_effect,
    stable_sigmoid,
)
from jobs.tools.jass_megacorpus_abcd_verdict import summarize_contrast
from jobs.tools.run_jass_gate_bounded import paired_opening_report
from jobs.tools.verify_optimizer_convergence import verify_optimizer_report


class MegaCorpusAbcdTest(unittest.TestCase):
    def test_optimizer_certificate_requires_actual_gtol(self):
        report = {
            "success": True,
            "status": 0,
            "iterations": 412,
            "gradient_inf_norm": 9.9e-5,
            "max_iterations": 2000,
            "maxcor": 20,
            "gtol": 1e-4,
            "message": "CONVERGENCE",
        }
        receipt = verify_optimizer_report(
            report,
            expected_max_iterations=2000,
            expected_maxcor=20,
            expected_gtol=1e-4,
        )
        self.assertEqual(receipt["iterations"], 412)
        report["gradient_inf_norm"] = 1.01e-4
        with self.assertRaisesRegex(ValueError, "stopped above gtol"):
            verify_optimizer_report(
                report,
                expected_max_iterations=2000,
                expected_maxcor=20,
                expected_gtol=1e-4,
            )

    def test_stable_sigmoid_extremes(self):
        values = stable_sigmoid(np.array([-1000.0, 0.0, 1000.0]))
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[1], 0.5)
        self.assertEqual(values[2], 1.0)

    def test_cluster_bootstrap_preserves_positive_effect(self):
        effect = np.array([0.1, 0.2, 0.3, 0.4])
        clusters = np.array([1, 1, 2, 2], dtype=np.uint64)
        report = cluster_bootstrap_effect(effect, clusters, samples=2000, seed=7)
        self.assertAlmostEqual(report["effect"], 0.25)
        self.assertGreater(report["ci_low"], 0.0)
        self.assertEqual(report["clusters"], 2)

    def test_paired_opening_report_is_colour_clustered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                {"game_index": i, "opening_index": i // 2, "pair_index": 0,
                 "a_is_white": not bool(i % 2), "score_a": score, "error": None}
                for i, score in enumerate((1.0, 0.5, 0.0, 0.5, 1.0, 1.0))
            ]
            for shard in range(2):
                selected = rows[shard::2]
                (root / f"games.{shard}.jsonl").write_text(
                    "".join(json.dumps(row) + "\n" for row in selected), encoding="utf-8"
                )
            report = paired_opening_report(
                [root / "games.0.jsonl", root / "games.1.jsonl"],
                expected_shards=2, expected_openings=3, pairs=1,
                bootstrap_samples=2000, seed=3,
            )
            self.assertAlmostEqual(report["rate"], 2.0 / 3.0)
            self.assertEqual(report["n_openings"], 3)
            self.assertEqual(report["games_per_opening"], 2)
            self.assertEqual(report["per_opening_scores"], [0.75, 0.25, 1.0])
            self.assertAlmostEqual(report["probability_rate_gt_half"], 0.749)

    def test_verdict_retains_positive_point_without_calling_established(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for view in ("q00", "native"):
                payload = {
                    "complete": True, "n": 500, "rate": 0.51,
                    "paired_opening": {
                        "method": "paired_colour_opening_cluster_bootstrap",
                        "n_openings": 250, "games_per_opening": 2,
                        "rate": 0.51, "ci_low": 0.47, "ci_high": 0.55,
                        "bootstrap_samples": 200000, "error_draws": 0,
                    },
                }
                (root / f"force-{view}-D_vs_A.json").write_text(json.dumps(payload))
            result = summarize_contrast(root, "D_vs_A", "curriculum", True)
            self.assertTrue(result["point_positive_both_views"])
            self.assertFalse(result["gain_established_both_views"])
            self.assertEqual(result["interpretation"], "positive_direction_not_established")


if __name__ == "__main__":
    unittest.main()
