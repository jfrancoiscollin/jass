#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/tb_frontier_symmetry_dedup.py"
spec = importlib.util.spec_from_file_location("tb_frontier_symmetry_dedup", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class SymmetryTests(unittest.TestCase):
    def test_rotation_and_color_swap_is_involution(self):
        fp = mod.format_fingerprint(1 << 0, 1 << 10, 1 << 1, 1 << 20, 0)
        sym = mod.symmetric_fingerprint(fp)
        wm, wk, bm, bk, stm = mod.parse_fingerprint(sym)
        self.assertEqual(wm, 1 << (49 - 1))
        self.assertEqual(wk, 1 << (49 - 20))
        self.assertEqual(bm, 1 << 49)
        self.assertEqual(bk, 1 << (49 - 10))
        self.assertEqual(stm, 1)
        self.assertEqual(mod.symmetric_fingerprint(sym), fp)
        self.assertEqual(mod.canonical_fingerprint(fp), mod.canonical_fingerprint(sym))

    def test_end_to_end_drops_symmetric_parent_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            groups = d / "groups.tsv"
            children = d / "children.jnnw"
            out_groups = d / "out.tsv"
            out_children = d / "out.jnnw"
            report = d / "report.json"

            fp = mod.format_fingerprint(1 << 0, 0, 1 << 1, 0, 0)
            sym = mod.symmetric_fingerprint(fp)
            rows = []
            for pid, parent_fp, stm in [(0, fp, 0), (1, sym, 1)]:
                for j, utility in enumerate((1, 0)):
                    rows.append({
                        "row_index": len(rows),
                        "parent_id": pid,
                        "parent_fingerprint": parent_fp,
                        "parent_stm": stm,
                        "from": 10 + j,
                        "to": 20 + j,
                        "num_captures": 1,
                        "promotes": 0,
                        "moving_king": 0,
                        "captured_kings": 0,
                        "parent_utility": utility,
                        "child_tb_wdl_stm": -utility,
                    })
            with groups.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=mod.FIELDS, delimiter="\t", lineterminator="\n")
                w.writeheader(); w.writerows(rows)
            rec = bytes(mod.REC_SIZE)
            children.write_bytes(b"JNNW" + struct.pack("<I", 4) + rec * 4)

            args = type("Args", (), {
                "groups": groups,
                "children": children,
                "out_groups": out_groups,
                "out_children": out_children,
                "report": report,
                "split_seed": 2026082801,
                "holdout_mod": 5,
                "min_holdout_parents": 800,
                "min_holdout_per_color": 250,
            })()
            r = mod.run(args)
            self.assertEqual(r["input_parents"], 2)
            self.assertEqual(r["unique_canonical_parents"], 1)
            self.assertEqual(r["symmetry_duplicates_removed"], 1)
            raw = out_children.read_bytes()
            self.assertEqual(struct.unpack_from("<I", raw, 4)[0], 2)
            with out_groups.open(newline="") as f:
                kept = list(csv.DictReader(f, delimiter="\t"))
            self.assertEqual(len(kept), 2)
            self.assertEqual({r["parent_fingerprint"] for r in kept}, {mod.canonical_fingerprint(fp)})


if __name__ == "__main__":
    unittest.main()
