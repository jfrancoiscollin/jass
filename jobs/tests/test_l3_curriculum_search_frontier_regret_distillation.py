import importlib.util
import pathlib
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "jobs/tools/l3_curriculum_search_frontier_regret_distillation.py"
spec = importlib.util.spec_from_file_location("frontier", PATH)
frontier = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(frontier)


class SearchFrontierRegretDistillationTests(unittest.TestCase):
    def test_rankdata_ties(self):
        got = frontier.rankdata(np.array([3.0, 1.0, 1.0, 2.0]))
        np.testing.assert_allclose(got, [4.0, 1.5, 1.5, 3.0])

    def test_feature_vector_is_shallow_only(self):
        row = {
            "historical_action": "12-17",
            "baseline_shallow_scores_cp": {
                "symmetrised": {"12-17": 2.0, "13-18": 12.0},
                "original": {"12-17": 1.0, "13-18": 11.0},
                "exact_image": {"12-17": 3.0, "13-18": 13.0},
            },
            "instability": {
                "depth_flips": 2,
                "orientation_disagreements": 1,
                "historical_mean_rank_fraction": 0.5,
                "score_volatility_cp": 70,
                "minimum_d9_margin_cp": 35,
            },
            "structural": {
                "legal_action_count": 2,
                "piece_count": 20,
                "king_count": 0,
                "phase": "midgame",
                "kings": "no_kings",
                "tactical": "quiet",
                "branching_bin": "b01_02",
            },
            # Deliberately extreme deep fields: feature extraction must ignore them.
            "accepted": False,
            "label": "unstable",
            "teacher_action": "13-18",
            "regret_cp_by_depth": {"10": 9999, "12": 9999},
        }
        values, names = frontier.feature_vector(row)
        self.assertEqual(values[0], 10.0)
        self.assertNotIn("accepted", names)
        self.assertNotIn("regret", " ".join(names).lower())
        self.assertNotIn("teacher", " ".join(names).lower())

    def test_fixed_ridge_prefers_signal(self):
        x = np.arange(40, dtype=float).reshape(-1, 1)
        y = np.arange(40, dtype=float)
        pred, _ = frontier.fit_predict(x[:30], y[:30], x[30:], 10.0)
        self.assertGreater(frontier.spearman(pred, y[30:]), 0.99)


if __name__ == "__main__":
    unittest.main()
