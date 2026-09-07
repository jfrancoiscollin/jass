from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ScanOracleGate0CpxAmendmentTests(unittest.TestCase):
    def test_amendment_is_explicitly_preexecution_and_preserves_science(self) -> None:
        doc = (ROOT / "docs/experiments/L3_SCAN_ORACLE_GATE0_PREEXECUTION_RUNTIME_AMENDMENT_V1_20260907.md").read_text(encoding="utf-8")
        self.assertIn("before the first Gate 0 execution", doc)
        self.assertIn("external EGDB build/probing: **OFF**", doc)
        self.assertIn("same frozen 512 parent IDs", doc)
        self.assertIn("zero new Scan searches, zero games, zero fits", doc)

    def test_cpx_wrapper_changes_only_runtime_environment_plumbing(self) -> None:
        wrapper = (ROOT / "jobs/templates/l3-scan-oracle-gate0-d3-retrospective-cpx-v1.sh").read_text(encoding="utf-8")
        self.assertIn("Gate0 retrospective must run on cpx62", wrapper)
        self.assertIn("external_egdb=OFF mirror_d3_equal_node_runtime=1", wrapper)
        self.assertIn('"$W/WDL_CONTROL.pjtw" - 20000 CONTROL', wrapper)
        self.assertIn('"$W/WDL_CONTROL.pjtw" - 20000 D3', wrapper)
        self.assertIn("if count != 1", wrapper)
        self.assertNotIn("SCAN_ORACLE_GATE0_GO=0", wrapper)

    def test_runtime_scorer_supports_explicit_external_egdb_off(self) -> None:
        source = (ROOT / "jobs/tools/scan_oracle_gate0_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn('if (egdb_dir != "-")', source)
        self.assertIn('"external_egdb_enabled"', source)
        self.assertIn("tb_cap = 0", source)


if __name__ == "__main__":
    unittest.main()
