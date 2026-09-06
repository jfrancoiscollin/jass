from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b3_parity as subject

BASE_FIELDS = [
    "row_index", "parent_id", "parent_fingerprint", "parent_stm", "parent_pieces",
    "from", "to", "num_captures", "promotes", "moving_king", "captured_kings",
    "material_count_delta_parent", "child_pieces", "child_legal_moves",
    "child_forced_capture", "child_rule_terminal", "child_tb_exact",
    "exact_parent_utility", "t_baseline_parent", "q5k_parent", "q50_parent",
    "q200_parent", "nodes5k", "nodes50k", "nodes200k", "completed_depth5k",
    "completed_depth50k", "completed_depth200k", "effective_depth5k",
    "effective_depth50k", "effective_depth200k", "aborted5k", "aborted50k",
    "aborted200k", "stop5k", "stop50k", "stop200k", "elapsed_us5k",
    "elapsed_us50k", "elapsed_us200k", "pv5k_enters_egdb", "pv50k_enters_egdb",
    "pv200k_enters_egdb",
]
EXTRA = [
    "searched5", "searched50", "searched200", "survived5", "survived50",
    "selected", "exact_shortcut_reason", "sole_survivor_reason", "uncertified",
]


def row(index: int, parent: int, *, exact: bool, q200: int = 0) -> dict[str, str]:
    value = {field: "0" for field in BASE_FIELDS}
    value.update({
        "row_index": str(index), "parent_id": str(parent),
        "parent_fingerprint": f"p{parent}", "parent_stm": str(parent % 2),
        "parent_pieces": "20", "from": str(index % 50), "to": str((index + 1) % 50),
        "child_pieces": "20", "child_legal_moves": "2",
        "child_rule_terminal": "1" if exact else "0",
        "child_tb_exact": "0", "exact_parent_utility": "1" if exact else "2",
        "q5k_parent": "10", "q50_parent": "20", "q200_parent": str(q200),
        "nodes5k": "5", "nodes50k": "50", "nodes200k": "200",
        "completed_depth5k": "3", "completed_depth50k": "5", "completed_depth200k": "7",
        "effective_depth5k": "3", "effective_depth50k": "5", "effective_depth200k": "7",
        "stop5k": "nodes", "stop50k": "nodes", "stop200k": "nodes",
    })
    return value


def write_tsv(path: Path, rows: list[dict[str, str]], header: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class B3ParityTests(unittest.TestCase):
    def fixture(self, root: Path, *, break_q200: bool = False):
        b2_rows: list[dict[str, str]] = []
        b3_rows: list[dict[str, str]] = []
        receipts = []
        index = 0
        for parent in range(4000):
            if parent == 0:
                ids = [index, index + 1]
                source_rows = [row(ids[0], parent, exact=False, q200=30),
                               row(ids[1], parent, exact=False, q200=20)]
                for source in source_rows:
                    adaptive = dict(source)
                    adaptive.update({field: "0" for field in EXTRA})
                    adaptive.update({
                        "searched5": "1", "searched50": "1", "searched200": "1",
                        "survived5": "1", "survived50": "1",
                        "selected": "1" if source["row_index"] == str(ids[0]) else "0",
                        "exact_shortcut_reason": "NONE", "sole_survivor_reason": "NONE",
                        "uncertified": "0",
                    })
                    b2_rows.append(source); b3_rows.append(adaptive)
                if break_q200:
                    b3_rows[-1]["searched200"] = "0"
                    b3_rows[-1]["nodes200k"] = "0"
                receipts.append({
                    "parent_id": parent, "S5_rows": ids, "S50_rows": ids,
                    "S200_charge_rows": ids, "pre_q200_choice_row_or_null": None,
                    "exact_shortcut_reason": None, "sole_survivor_reason": None,
                    "uncertified_shadow": False, "shadow_nodes_total": 510,
                })
                index += 2
            else:
                source = row(index, parent, exact=True)
                adaptive = dict(source)
                for field in ("q5k_parent", "q50_parent", "q200_parent", "nodes5k", "nodes50k",
                              "nodes200k", "completed_depth5k", "completed_depth50k",
                              "completed_depth200k", "effective_depth5k", "effective_depth50k",
                              "effective_depth200k"):
                    adaptive[field] = "0"
                adaptive.update({field: "0" for field in EXTRA})
                adaptive.update({
                    "selected": "1", "exact_shortcut_reason": "EXACT_WIN",
                    "sole_survivor_reason": "NONE", "uncertified": "0",
                    "stop5k": "none", "stop50k": "none", "stop200k": "none",
                })
                b2_rows.append(source); b3_rows.append(adaptive)
                receipts.append({
                    "parent_id": parent, "S5_rows": [], "S50_rows": [],
                    "S200_charge_rows": [], "pre_q200_choice_row_or_null": index,
                    "exact_shortcut_reason": "EXACT_WIN", "sole_survivor_reason": None,
                    "uncertified_shadow": False, "shadow_nodes_total": 0,
                })
                index += 1
        b2 = root / "b2.tsv"; b3 = root / "b3.tsv"; rec = root / "receipts.jsonl"
        write_tsv(b2, b2_rows, BASE_FIELDS)
        write_tsv(b3, b3_rows, BASE_FIELDS + EXTRA)
        rec.write_text("".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
                               for item in receipts), encoding="utf-8")
        return b2, rec, b3

    def test_full_population_parity_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = subject.compare(*self.fixture(Path(tmp)))
            self.assertEqual(report["verdict"], subject.VERDICT)
            self.assertEqual(report["parents"], 4000)
            self.assertEqual(report["actual_searches"], {"5": 2, "50": 2, "200": 2})
            self.assertEqual(report["total_nodes"], 510)
            self.assertIn(1, report["zero_cost_parent_ids"])

    def test_missing_real_q200_search_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = subject.compare(*self.fixture(Path(tmp), break_q200=True))
            self.assertEqual(report["verdict"], "B3_REAL_ADAPTIVE_TEACHER_PARITY_BLOCKED_V1")
            self.assertTrue(report["mismatches"])


if __name__ == "__main__":
    unittest.main()
