from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from jobs.tools import scan_oracle_gate0_select as select
from jobs.tools import scan_oracle_gate0_render as render

ROOT = Path(__file__).resolve().parents[2]


class ScanOracleGate0Tests(unittest.TestCase):
    def test_selector_is_exact_target_blind_and_phase_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "groups.tsv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["parent_id", "parent_fingerprint", "parent_phase"],
                    delimiter="\t",
                )
                writer.writeheader()
                for pid in range(2000):
                    phase = select.PHASES[pid // 500]
                    writer.writerow({
                        "parent_id": pid,
                        "parent_fingerprint": f"fingerprint-{pid:04d}",
                        "parent_phase": phase,
                    })
            meta = select.load_parent_meta(path)
            a = select.select(meta)
            b = select.select(meta)
            self.assertEqual(a, b)
            self.assertEqual(len(a), 512)
            self.assertEqual(len(set(a)), 512)
            for phase in select.PHASES:
                self.assertEqual(sum(meta[pid][1] == phase for pid in a), 128)

    def test_gate0_contract_does_not_read_d3_match_outcomes(self) -> None:
        prereg = (ROOT / "docs/experiments/L3_SCAN_ORACLE_GATE0_V1_20260907.md").read_text(encoding="utf-8")
        stage = (ROOT / "jobs/templates/l3-scan-oracle-gate0-d3-retrospective-v1.sh").read_text(encoding="utf-8")
        readout = (ROOT / "jobs/tools/scan_oracle_gate0_readout.py").read_text(encoding="utf-8")
        self.assertIn("Scan 3.1 sibling scores at exactly requested 200,000 nodes", prereg)
        self.assertIn("SCAN-GATE0-2026090701:", prereg)
        self.assertIn("bootstrap 95% LCB", prereg)
        self.assertNotIn("cpx62-1857", stage)
        self.assertNotIn("D3_RUNTIME_EQUAL_NODE", stage)
        self.assertNotIn("elo", readout.lower())
        self.assertIn("BOOTSTRAPS = 20_000", readout)
        self.assertIn("SEED = 2026090702", readout)

    def test_runtime_scorer_is_exact_node_and_zero_game(self) -> None:
        source = (ROOT / "jobs/tools/scan_oracle_gate0_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("budget != 20'000", source)
        self.assertIn("limits.node_limit_mode = NodeLimitMode::Exact", source)
        self.assertIn("limits.threads = 1", source)
        self.assertIn("fresh_engine_each_parent", source)
        self.assertIn('arm != "CONTROL" && arm != "D3"', source)
        self.assertIn('"  \\"strength_games\\": 0', source)

    def test_cmake_renderer_is_isolated_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "CMakeLists.txt"
            path.write_text("add_library(jass_lib STATIC x.cpp)\nadd_library(jass_t3_f6_runtime OBJECT y.cpp)\n", encoding="utf-8")
            render.render(path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("jass_scan_oracle_gate0_runtime", text)
            with self.assertRaises(RuntimeError):
                render.render(path)


if __name__ == "__main__":
    unittest.main()
