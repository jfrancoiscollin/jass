from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Gate0VariantRecoveryTests(unittest.TestCase):
    def test_reuses_j1_j2_and_only_reruns_missing_arms(self) -> None:
        text = (ROOT / "jobs/templates/l3-scan-oracle-gate0-search-variants-recovery-v1.sh").read_text(encoding="utf-8")
        self.assertIn("reuse=J1,J2 rerun=J3,J4,J5,J6", text)
        self.assertIn("--expected-state failed", text)
        self.assertIn("20260907T202147Z-e80beb59", text)
        self.assertIn("cp \"$IN/J1.tsv\"", text)
        self.assertIn("cp \"$IN/J2.tsv\"", text)
        self.assertNotIn("score=J1_SCAN_VERIFY", text)
        self.assertNotIn("score=J2_SCAN_THREAT_REENTRY", text)

    def test_no_activation_becomes_screen_result_not_stage_abort(self) -> None:
        text = (ROOT / "jobs/templates/l3-scan-oracle-gate0-search-variants-recovery-v1.sh").read_text(encoding="utf-8")
        self.assertIn("activation-sentinel patch anchor drift", text)
        self.assertIn("no observed activation is a screen result, not a stage failure", text)
        self.assertIn("observed_activation", text)
        self.assertIn("gate=='GATE0_SUPPORTED' and activated", text)

    def test_no_new_teacher_or_strength_side_effects(self) -> None:
        text = (ROOT / "jobs/templates/l3-scan-oracle-gate0-search-variants-recovery-v1.sh").read_text(encoding="utf-8")
        self.assertIn("new_scan_searches':0", text)
        self.assertIn("new_strength_games':0", text)
        self.assertIn("new_fits':0", text)
        self.assertNotIn("--gen-opening-pool", text)
        self.assertNotIn("selfplay", text.lower().replace("new_selfplay_games", ""))


if __name__ == "__main__":
    unittest.main()
