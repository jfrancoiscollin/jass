from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Gate0SearchVariantTests(unittest.TestCase):
    def test_frozen_six_arms_and_cheap_budget(self) -> None:
        src = (ROOT / "jobs/tools/scan_oracle_gate0_search_variants.cpp").read_text(encoding="utf-8")
        for arm in (
            "J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY", "J3_SCAN_SINGLE_REPLY",
            "J4_SCAN_LMR", "J5_SCAN_ORDERING", "J6_NO_NULL_MOVE",
        ):
            self.assertIn(arm, src)
        self.assertIn("budget != 20'000", src)
        self.assertIn("external_egdb_enabled", src)
        self.assertIn("fresh_engine_each_parent", src)
        self.assertIn("scan_verify_pruning = true", src)
        self.assertIn("scan_threat_reentry = true", src)
        self.assertIn("ext_single_reply = true", src)
        self.assertIn("scan_lmr_semantics = true", src)
        self.assertIn("scan_probabilistic_ordering = true", src)
        self.assertIn("disable_null_move = true", src)

    def test_stage_reuses_1864_control_and_scan_without_new_scan(self) -> None:
        text = (ROOT / "jobs/templates/l3-scan-oracle-gate0-search-variants-v1.sh").read_text(encoding="utf-8")
        self.assertIn("cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1", text)
        self.assertIn("gate0-control.tsv", text)
        self.assertIn("scan_searches_planned=0", text)
        self.assertIn("ARMS=(J1_SCAN_VERIFY", text)
        self.assertIn("planned_candidate_nodes':6*512*20000", text)
        self.assertIn("fresh_confirmation_required_before_strength", text)
        self.assertIn("strength_authorized':False", text)
        self.assertNotIn("--gen-opening-pool", text)
        self.assertNotIn("strength_games=1", text)

    def test_cmake_renderer_exposes_variant_target(self) -> None:
        text = (ROOT / "jobs/tools/scan_oracle_gate0_render.py").read_text(encoding="utf-8")
        self.assertIn("jass_scan_oracle_gate0_runtime", text)
        self.assertIn("jass_scan_oracle_gate0_search_variants", text)


if __name__ == "__main__":
    unittest.main()
