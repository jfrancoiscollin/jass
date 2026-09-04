#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "adaptive_sibling_teacher_shadow.py"
SPEC = importlib.util.spec_from_file_location("adaptive_shadow", TOOL)
assert SPEC is not None and SPEC.loader is not None
shadow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shadow
SPEC.loader.exec_module(shadow)

FIELDS = [
    "row_index",
    "parent_id",
    "child_rule_terminal",
    "child_tb_exact",
    "exact_parent_utility",
    "q5k_parent",
    "q50_parent",
    "q200_parent",
    "nodes5k",
    "nodes50k",
    "nodes200k",
]


def row(
    row_index: int,
    parent_id: int,
    q5: int,
    q50: int,
    q200: int,
    *,
    exact_utility: int | None = None,
    terminal: bool = False,
    tb: bool = False,
    n5: int = 5000,
    n50: int = 50000,
    n200: int = 200000,
) -> dict[str, str]:
    return {
        "row_index": str(row_index),
        "parent_id": str(parent_id),
        "child_rule_terminal": str(int(terminal)),
        "child_tb_exact": str(int(tb)),
        "exact_parent_utility": str(2 if exact_utility is None else exact_utility),
        "q5k_parent": str(q5),
        "q50_parent": str(q50),
        "q200_parent": str(q200),
        "nodes5k": str(n5),
        "nodes50k": str(n50),
        "nodes200k": str(n200),
    }


class AdaptiveShadowTests(unittest.TestCase):
    def write_groups(self, records: list[dict[str, str]]) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False)
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def test_shadow_saves_nodes_without_using_q200_for_survival(self) -> None:
        records = [
            row(0, 10, 300, 400, 500),
            row(1, 10, 250, 300, 400),
            # Deliberately best at q200, but it must be eliminated by q5.
            row(2, 10, 0, 1000, 900),
        ]
        rows = shadow.load_groups(self.write_groups(records))
        report, results = shadow.build_report(rows)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.survivors50, (0, 1))
        self.assertEqual(result.survivors200, (0, 1))
        self.assertEqual(result.shadow_choice, 0)
        self.assertEqual(result.reference_choice, 2)
        self.assertEqual(result.regret_cp, 400)
        self.assertEqual(result.full_nodes, 765000)
        self.assertEqual(result.shadow_nodes, 515000)
        self.assertGreater(report["teacher_node_saving"], 0.0)
        self.assertFalse(report["policy"]["q200_used_for_survival"])
        self.assertFalse(report["policy"]["real_adaptive_teacher_authorized"])

    def test_minimum_two_survivors_is_deterministic(self) -> None:
        records = [
            row(5, 11, 300, 500, 600),
            row(3, 11, 300, 100, 200),
            row(8, 11, 0, 0, 0),
        ]
        rows = shadow.load_groups(self.write_groups(records))
        _, results = shadow.build_report(rows)
        # q5 tie breaks by row_index, then both tied top rows survive.
        self.assertEqual(results[0].survivors50, (3, 5))
        # At q50, the minimum-two rule keeps both despite the 400 cp gap.
        self.assertEqual(results[0].survivors200, (5, 3))

    def test_exact_win_shortcuts_parent_at_zero_shadow_cost(self) -> None:
        records = [
            row(0, 20, 0, 0, 0, exact_utility=1, terminal=True),
            row(1, 20, 999, 999, 999),
        ]
        rows = shadow.load_groups(self.write_groups(records))
        report, results = shadow.build_report(rows)
        result = results[0]
        self.assertTrue(result.exact_win_shortcut)
        self.assertEqual(result.shadow_nodes, 0)
        self.assertEqual(result.shadow_choice, 0)
        self.assertEqual(result.reference_choice, 0)
        self.assertEqual(result.regret_cp, 0)
        self.assertEqual(report["exact_win_shortcut_parents"], 1)

    def test_cli_writes_json_and_decisions(self) -> None:
        records = [row(0, 30, 100, 100, 100), row(1, 30, 90, 90, 90)]
        groups = self.write_groups(records)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "report.json"
            decisions = Path(directory) / "decisions.tsv"
            rc = shadow.main(
                ["--groups", str(groups), "--out", str(out), "--decisions-out", str(decisions)]
            )
            self.assertEqual(rc, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "jass.adaptive_sibling_teacher_shadow.v1")
            self.assertEqual(report["fits"], 0)
            self.assertEqual(report["searches"], 0)
            self.assertFalse(report["promotion_authorized"])
            self.assertIn("parent_id", decisions.read_text(encoding="utf-8").splitlines()[0])

    def test_missing_columns_fail_closed(self) -> None:
        tmp = tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", delete=False)
        with tmp:
            tmp.write("row_index\tparent_id\n0\t1\n")
        path = Path(tmp.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            shadow.load_groups(path)


if __name__ == "__main__":
    unittest.main()
