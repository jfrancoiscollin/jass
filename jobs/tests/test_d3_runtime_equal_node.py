from pathlib import Path
import unittest

from jobs.tools import d3_runtime_equal_node_pool as pool
from jobs.tools import d3_runtime_equal_node_readout as readout
from jobs.tools import d3_runtime_equal_node_render as render


ROOT = Path(__file__).resolve().parents[2]


class D3RuntimeEqualNodeTests(unittest.TestCase):
    def test_frozen_constants(self):
        self.assertEqual(pool.CANDIDATES, 30000)
        self.assertEqual(pool.PRIMARY, 750)
        self.assertEqual(pool.HARNESS, 100)
        self.assertEqual(pool.GENERATION_SEED, 2026111301)
        self.assertEqual(pool.SELECTION_PREFIX, "2026111302:")
        self.assertEqual(readout.BOOTSTRAP, 200000)
        self.assertEqual(readout.BOOTSTRAP_SEED, 2026111303)
        self.assertEqual(readout.NODE_BUDGET, 20000)

    def test_target_blind_split_is_deterministic_and_disjoint(self):
        unique = {f"id-{i:04d}": f"fen-{i:04d}" for i in range(1000)}
        p1, h1 = pool.select_unique(unique, set())
        p2, h2 = pool.select_unique(dict(reversed(list(unique.items()))), set())
        self.assertEqual(p1, p2)
        self.assertEqual(h1, h2)
        self.assertEqual(len(p1), 750)
        self.assertEqual(len(h1), 100)
        self.assertFalse({x[0] for x in p1} & {x[0] for x in h1})

    def test_exact_node_hub_render_is_symmetric(self):
        hub = (ROOT / "src/hub.cpp").read_text(encoding="utf-8")
        control = render.render_hub(hub, candidate=False)
        candidate = render.render_hub(hub, candidate=True)
        for text in (control, candidate):
            self.assertIn('tok == "nodes"', text)
            self.assertIn("lim.max_nodes = static_cast<std::uint64_t>(v);", text)
            self.assertIn("lim.node_limit_mode = NodeLimitMode::Exact;", text)
            self.assertIn("|| nodes_set", text)
        self.assertNotIn("d3calls=", control)
        self.assertIn("d3calls=", candidate)
        self.assertIn("reset_feature_calls()", candidate)

    def test_candidate_counter_is_diagnostic_only(self):
        header = (ROOT / "src/d3_runtime_move_order.hpp").read_text(encoding="utf-8")
        rendered = render.render_header(header)
        self.assertIn("FEATURE_CALLS.fetch_add(1, std::memory_order_relaxed);", rendered)
        self.assertIn("reset_feature_calls()", rendered)
        self.assertIn("return parent_value + residual(rt, parent, move, child);", rendered)

    def test_elo_direction(self):
        self.assertGreater(readout.elo(0.51), 0.0)
        self.assertLess(readout.elo(0.49), 0.0)
        self.assertAlmostEqual(readout.elo(0.5), 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
