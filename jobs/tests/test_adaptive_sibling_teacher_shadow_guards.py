#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "adaptive_sibling_teacher_shadow.py"
SPEC = importlib.util.spec_from_file_location("adaptive_shadow_guards", TOOL)
assert SPEC is not None and SPEC.loader is not None
shadow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shadow
SPEC.loader.exec_module(shadow)
FIELDS = sorted(shadow.REQUIRED_COLUMNS)


def base(row_index: int, parent_id: int) -> dict[str, str]:
    values = {
        "row_index": row_index, "parent_id": parent_id,
        "child_rule_terminal": 0, "child_tb_exact": 0,
        "exact_parent_utility": 2,
        "q5k_parent": 0, "q50_parent": 0, "q200_parent": 0,
        "nodes5k": 5000, "nodes50k": 50000, "nodes200k": 200000,
    }
    return {k: str(values[k]) for k in FIELDS}


class GuardTests(unittest.TestCase):
    def write(self, rows: list[dict[str, str]]) -> Path:
        f = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False)
        with f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
            w.writeheader(); w.writerows(rows)
        p = Path(f.name); self.addCleanup(p.unlink, missing_ok=True); return p

    def test_exactness_flags_must_be_binary(self) -> None:
        r = base(0, 1); r["child_tb_exact"] = "2"
        with self.assertRaisesRegex(ValueError, "flags must be 0/1"):
            shadow.load_groups(self.write([r]))

    def test_nonexact_requires_utility_sentinel(self) -> None:
        r = base(0, 1); r["exact_parent_utility"] = "0"
        with self.assertRaisesRegex(ValueError, "sentinel 2"):
            shadow.load_groups(self.write([r]))

    def test_negative_nodes_fail_closed(self) -> None:
        r = base(0, 1); r["nodes200k"] = "-1"
        with self.assertRaisesRegex(ValueError, "non-negative"):
            shadow.load_groups(self.write([r]))

    def test_full_ladder_counts_historical_exact_row_cost(self) -> None:
        a = base(0, 1); a["child_rule_terminal"] = "1"; a["exact_parent_utility"] = "1"
        b = base(1, 1)
        rows = shadow.load_groups(self.write([a, b]))
        report, results = shadow.build_report(rows)
        self.assertEqual(results[0].full_nodes, 510000)
        self.assertEqual(results[0].shadow_nodes, 0)
        self.assertEqual(report["node_ratio"], 0.0)

    def test_sole_unresolved_survivor_skips_q200(self) -> None:
        exact_draw = base(0, 2)
        exact_draw["child_tb_exact"] = "1"; exact_draw["exact_parent_utility"] = "0"
        unresolved = base(1, 2)
        rows = shadow.load_groups(self.write([exact_draw, unresolved]))
        _, results = shadow.build_report(rows)
        result = results[0]
        self.assertTrue(result.uncertified_shadow)
        self.assertEqual(result.survivors200, (1,))
        self.assertEqual(result.shadow_nodes, 55000)


if __name__ == "__main__":
    unittest.main()
