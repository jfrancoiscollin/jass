#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / "tools/mine_conversion_pool.py"
SPEC = importlib.util.spec_from_file_location("mine_conversion_pool", MODULE)
MP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MP)


class MineConversionPoolTests(unittest.TestCase):
    def test_holdout_only_can_use_more_than_half_of_fresh_pool(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pool = root / "pool.fen"
            rows = []
            for index in range(10):
                # margin=1 -> p3_mince; positions are deliberately unique.
                rows.append(f"W:W{index + 1},30:B31  # source=fresh\n")
            pool.write_text("".join(rows), encoding="utf-8")
            out_eval, out_train = root / "eval.fen", root / "train.fen"
            manifest = root / "manifest.json"
            rc = MP.do_carve(Namespace(
                pool=str(pool), per_palier=8, holdout_only=True,
                out_eval=str(out_eval), out_train=str(out_train),
                manifest=str(manifest),
            ))
            self.assertEqual(rc, 0)
            selected = [
                line for line in out_eval.read_text().splitlines()
                if line and not line.startswith("#")
            ]
            self.assertEqual(len(selected), 8)
            self.assertTrue(all("palier=p3_mince" in line for line in selected))


if __name__ == "__main__":
    unittest.main()
