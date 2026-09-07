from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import d4b_runtime_render

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_D4B_SEARCH_UTILITY_MICRO_SCREEN_V1_20260907.json"


class D4bMicroTests(unittest.TestCase):
    def test_prereg_is_cheap_and_zero_strength(self) -> None:
        p = json.loads(PREREG.read_text(encoding="utf-8"))
        self.assertEqual(p["roots"]["total"], 512)
        self.assertEqual(p["teacher"]["exact_nodes_per_root"], 20000)
        self.assertEqual(p["teacher"]["planned_nodes"], 10240000)
        self.assertEqual(p["examples"]["exact_counts"], {"train": 8000, "valid": 1000, "test": 1000})
        self.assertFalse(p["examples"]["phase_quota_gate"])
        self.assertEqual(p["model"]["trainable_parameters"], 96)
        self.assertEqual(p["model"]["fits"], 1)
        self.assertEqual(p["scan_gate0"]["parents"], 512)
        self.assertEqual(p["scan_gate0"]["new_scan_searches"], 0)
        self.assertEqual(p["authorization"]["strength_games"], 0)
        self.assertEqual(p["authorization"]["selfplay_games"], 0)
        self.assertFalse(p["authorization"]["promotion"])

    def test_stage_reuses_only_d4_roots_and_stops_before_gate0_on_offline_fail(self) -> None:
        s = (ROOT / "jobs/templates/l3-d4b-search-utility-micro-screen-v1.sh").read_text(encoding="utf-8")
        self.assertIn("--file artefacts/d4-search-utility-roots.tsv=d4-roots.tsv", s)
        self.assertNotIn("s00-events.jsonl=", s)
        self.assertIn("D4B_MICRO_OFFLINE_SUPPORTED_V1", s)
        self.assertIn("stop before Scan Gate0", s)
        self.assertIn("teacher_nodes_per_root=20000", s)
        self.assertIn("new_scan_searches=0", s)
        self.assertIn("STRENGTH_GAMES__0", s)

    def test_runtime_renderer_is_internal_stable_hoist(self) -> None:
        source = ROOT / "src/search.cpp"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "search.cpp"
            d4b_runtime_render.render(source, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("ply < 1", text)
            self.assertIn("depth < 3", text)
            self.assertIn("n < 2 || n > 16", text)
            self.assertIn("if (tt_hit && moves[i] == tt_move) continue", text)
            self.assertIn("d4b_runtime_order::logit", text)
            self.assertIn("moves[candidate_index[0]] = selected", text)
            self.assertNotIn("order_moves(root_moves", text)

    def test_runtime_loader_is_width96_and_fail_closed(self) -> None:
        h = (ROOT / "src/d4b_runtime_move_order.hpp").read_text(encoding="utf-8")
        self.assertIn("WIDTH = FEATURE_WIDTH * PHASES", h)
        self.assertIn("JASS_D4B_RUNTIME_MODEL", h)
        self.assertIn("D4B_RUNTIME_INVALID", h)
        self.assertIn("model npy payload size mismatch", h)


if __name__ == "__main__":
    unittest.main()
