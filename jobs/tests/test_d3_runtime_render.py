from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "jobs/tools/d3_runtime_render.py"
spec = importlib.util.spec_from_file_location("d3_runtime_render", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class D3RuntimeRenderTests(unittest.TestCase):
    def _fixture(self) -> str:
        return (
            '#include "scan_sacs.hpp"\n'
            + mod.OLD_ORDER
            + '\nvoid recurse(){ '
            + mod.CALL_OLD
            + ' }\n'
            + mod.ROOT_ANCHOR
        )

    def test_render_exact_contract(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "search.cpp"
            out = Path(td) / "candidate.cpp"
            src.write_text(self._fixture(), encoding="utf-8")
            mod.render(src, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn('#include "d3_runtime_move_order.hpp"', text)
            self.assertIn('d3_runtime_order::score(d3, parent, moves[i])', text)
            self.assertIn('order_moves(moves, *this, pos, ply', text)
            self.assertIn('order_moves(root_moves, s, pos, 0, Move{}, false, Move{});', text)
            self.assertIn('if (!d3.active || d3_runtime_order::phase_index(parent) < 0)', text)
            self.assertIn('scores[j] > scores[best]', text)
            self.assertIn('semantic_less(moves[j], moves[best])', text)

    def test_missing_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "search.cpp"
            out = Path(td) / "candidate.cpp"
            src.write_text(self._fixture().replace(mod.CALL_OLD, "drift();"), encoding="utf-8")
            with self.assertRaises(SystemExit):
                mod.render(src, out)

    def test_duplicate_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "search.cpp"
            out = Path(td) / "candidate.cpp"
            src.write_text(self._fixture() + mod.CALL_OLD, encoding="utf-8")
            with self.assertRaises(SystemExit):
                mod.render(src, out)


if __name__ == "__main__":
    unittest.main()
