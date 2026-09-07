from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from jobs.tools import d4_search_utility_offline as d4
from jobs.tools import d4_search_utility_pool as pool
from jobs.tools import d4_search_utility_trace_render as render

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_D4_SEARCH_UTILITY_ORDERING_PREREGISTRATION_V1_20260907.json"
TIE_AMENDMENT = ROOT / "docs/experiments/L3_D4_SEARCH_UTILITY_EXAMPLE_TIE_AMENDMENT_V1_20260907.md"


class D4SearchUtilityOfflineTests(unittest.TestCase):
    def test_frozen_contract_constants_match_preregistration(self) -> None:
        p = json.loads(PREREG.read_text(encoding="utf-8"))
        self.assertEqual(pool.CANDIDATES, p["dataset"]["candidate_roots"])
        self.assertEqual(pool.SELECTED, p["dataset"]["selected_roots"])
        self.assertEqual(pool.GENERATION_SEED, p["dataset"]["generation_seed"])
        self.assertEqual(pool.SELECTION_PREFIX, p["dataset"]["selector_prefix"])
        self.assertEqual(d4.FEATURE_WIDTH, p["model"]["features_per_phase"])
        self.assertEqual(d4.WIDTH, p["model"]["trainable_parameters"])
        self.assertEqual(d4.L2, p["model"]["l2"])
        self.assertEqual(d4.MAX_ITER, p["model"]["max_iter"])
        self.assertEqual(d4.MAXCOR, p["model"]["maxcor"])
        self.assertEqual(d4.GTOL, p["model"]["gtol"])
        self.assertEqual(d4.BOOTSTRAPS, p["offline_gate"]["bootstrap_repetitions"])
        self.assertEqual(d4.BOOTSTRAP_SEED, p["offline_gate"]["bootstrap_seed"])
        self.assertEqual(list(d4.FEATURES), p["features"])
        self.assertEqual(d4.EXACT_COUNTS, p["dataset"]["examples"])

    def test_root_split_is_exact_and_preteacher(self) -> None:
        self.assertEqual(pool.split_for_index(0), "train")
        self.assertEqual(pool.split_for_index(3199), "train")
        self.assertEqual(pool.split_for_index(3200), "valid")
        self.assertEqual(pool.split_for_index(3599), "valid")
        self.assertEqual(pool.split_for_index(3600), "test")
        self.assertEqual(pool.split_for_index(3999), "test")
        with self.assertRaises(ValueError):
            pool.split_for_index(4000)

    def test_loss_gradient_matches_finite_difference(self) -> None:
        rng = np.random.default_rng(2026111598)
        n = 11
        x = rng.normal(0.0, 0.2, size=(n, 4, d4.FEATURE_WIDTH))
        mask = np.ones((n, 4), dtype=bool)
        mask[::3, 3] = False
        phase = np.asarray([i % 4 for i in range(n)], dtype=np.int8)
        labels = np.asarray([i % (3 if not mask[i, 3] else 4) for i in range(n)], dtype=np.int8)
        beta = rng.normal(0.0, 0.05, size=d4.WIDTH)
        loss, grad = d4.loss_grad(beta.copy(), x, mask, phase, labels)
        self.assertTrue(np.isfinite(loss))
        eps = 1e-6
        for index in (0, 7, 23, 24, 47, 72, 95):
            plus = beta.copy(); plus[index] += eps
            minus = beta.copy(); minus[index] -= eps
            numeric = (d4.loss_grad(plus, x, mask, phase, labels)[0]
                       - d4.loss_grad(minus, x, mask, phase, labels)[0]) / (2 * eps)
            self.assertAlmostEqual(float(grad[index]), float(numeric), places=6)

    def test_zero_beta_reproduces_legacy_top4_order(self) -> None:
        x = np.zeros((4, 4, d4.FEATURE_WIDTH), dtype=np.float64)
        mask = np.ones((4, 4), dtype=bool)
        phase = np.asarray([0, 1, 2, 3], dtype=np.int8)
        score = d4.logits(np.zeros(d4.WIDTH), x, mask, phase)
        self.assertTrue(np.array_equal(np.argmax(score, axis=1), np.zeros(4, dtype=int)))
        self.assertTrue(np.array_equal(score[0], np.asarray([0.0, -1.0, -2.0, -3.0])))

    def test_same_key_occurrence_tie_rule_matches_preexecution_amendment(self) -> None:
        amendment = TIE_AMENDMENT.read_text(encoding="utf-8")
        source = (ROOT / "jobs/tools/d4_search_utility_offline.py").read_text(encoding="utf-8")
        self.assertIn("ascending integer `(root_index, event_index)`", amendment)
        self.assertIn("item = (invert_digest(primary), -root_index, -event_index, payload)", source)
        self.assertIn("rows.sort(key=lambda row: (row[0], row[1], row[2]))", source)
        self.assertNotIn("tie_text = f\"{int(event['root_index'])}:{int(event['event_index'])}:{key}\"", source)

    def test_trace_renderer_is_isolated_exact_and_fail_closed(self) -> None:
        render.self_test()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            shutil.copy2(ROOT / "src/search.hpp", root / "src/search.hpp")
            shutil.copy2(ROOT / "src/search.cpp", root / "src/search.cpp")
            shutil.copy2(ROOT / "CMakeLists.txt", root / "CMakeLists.txt")
            render.render(root)
            hpp = (root / "src/search.hpp").read_text(encoding="utf-8")
            cpp = (root / "src/search.cpp").read_text(encoding="utf-8")
            cmake = (root / "CMakeLists.txt").read_text(encoding="utf-8")
            self.assertIn("SearchUtilityTrace* search_utility_trace", hpp)
            self.assertIn("d4_trace_moves", cpp)
            self.assertIn("if (!stopped && d4_trace_eligible)", cpp)
            self.assertIn("d4_search_utility_trace_export", cmake)
            with self.assertRaises(RuntimeError):
                render.render(root)

    def test_exporter_does_not_consume_forbidden_targets(self) -> None:
        text = (ROOT / "jobs/tools/d4_search_utility_trace_export.cpp").read_text(encoding="utf-8")
        self.assertNotIn("SearchDecisionTrace trace", text)
        self.assertNotIn("JASS_D3_RUNTIME_ADAPTER=", text)
        self.assertIn("max_nodes = 50'000", text)
        self.assertIn("NodeLimitMode::Exact", text)
        self.assertIn("limits.threads = 1", text)


if __name__ == "__main__":
    unittest.main()
