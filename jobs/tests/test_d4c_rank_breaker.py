from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import d4c_runtime_render

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_D4C_RANK_BREAKER_MICRO_V1_20260908.json"


class D4cRankBreakerTests(unittest.TestCase):
    def test_prereg_is_one_fit_zero_strength(self) -> None:
        p = json.loads(PREREG.read_text(encoding="utf-8"))
        self.assertEqual(p["roots"]["total"], 512)
        self.assertEqual(p["teacher"]["exact_nodes_per_root"], 20000)
        self.assertEqual(p["teacher"]["planned_nodes"], 10240000)
        self.assertEqual(p["model"]["objective"], "pairwise_label_vs_other_logistic")
        self.assertEqual(p["model"]["trainable_parameters"], 96)
        self.assertFalse(p["model"]["fixed_legacy_logit"])
        self.assertTrue(p["model"]["legacy_rank_feature_retained"])
        self.assertEqual(p["model"]["fits"], 1)
        self.assertEqual(p["model"]["model_searches"], 0)
        self.assertEqual(p["scan_gate0"]["new_scan_searches"], 0)
        self.assertEqual(p["authorization"]["strength_games"], 0)
        self.assertFalse(p["authorization"]["strength_authorized"])

    def test_stage_authenticates_d4b_motivation_and_stops_offline(self) -> None:
        s = (ROOT / "jobs/templates/l3-d4c-rank-breaker-micro-screen-v1.sh").read_text(encoding="utf-8")
        self.assertIn("D4B_MICRO_GATE0_NOT_SUPPORTED_V1", s)
        self.assertIn("d4b_eligible_nodes')!=216779", s)
        self.assertIn("d4b_hoists')!=71", s)
        self.assertIn("D4C_RANK_BREAKER_OFFLINE_SUPPORTED_V1", s)
        self.assertIn("stop before Scan Gate0", s)
        self.assertIn("new_scan_searches=0", s)
        self.assertIn("STRENGTH_GAMES__0", s)

    def test_runtime_renderer_removes_fixed_rank_logit_and_keeps_stable_hoist(self) -> None:
        source = ROOT / "src/search.cpp"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "search.cpp"
            d4c_runtime_render.render(source, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("d4c_runtime_order::score(rt, phase, f)", text)
            self.assertIn("d4c_runtime_order::note_prediction(best)", text)
            self.assertIn("moves[candidate_index[0]] = selected", text)
            self.assertIn("if (tt_hit && moves[i] == tt_move) continue", text)
            self.assertNotIn("d4b_runtime_order", text)
            self.assertNotIn("order_moves(root_moves", text)

    def test_runtime_loader_and_diagnostics(self) -> None:
        h = (ROOT / "src/d4c_runtime_move_order.hpp").read_text(encoding="utf-8")
        self.assertIn("JASS_D4C_RUNTIME_MODEL", h)
        self.assertIn("D4C_RUNTIME_INVALID", h)
        self.assertIn("double s = 0.0", h)
        self.assertIn("g_predicted_rank", h)
        self.assertIn("note_prediction", h)
        self.assertNotIn("legacy_rank", h)

    def test_pairwise_tool_has_no_search_loop(self) -> None:
        t = (ROOT / "jobs/tools/d4c_rank_breaker.py").read_text(encoding="utf-8")
        self.assertIn("pairwise_label_vs_other_logistic", t)
        self.assertIn("x[i, y] - x[i, j]", t)
        self.assertIn("test_change_rate_ge_0p01", t)
        self.assertIn("test_correct_nonfirst_override_rate_ge_0p05", t)
        self.assertNotIn("model_search", t.replace('"model_searches": 0', ""))


if __name__ == "__main__":
    unittest.main()
