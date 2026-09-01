from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "templates" / "jfi-force-common-v1.sh"
POOL1 = ROOT / "templates" / "l3-jfi-e-force-pool1-v1.sh"
POOL2 = ROOT / "templates" / "l3-jfi-e-force-pool2-v1.sh"


class JfiEProtocolTests(unittest.TestCase):
    def test_common_freezes_models_topology_and_complete_exclusion_registry(self):
        text = COMMON.read_text()
        self.assertIn("319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1", text)
        self.assertIn("JFI_BOOTSTRAP=200000", text)
        self.assertIn("JFI_OPENINGS=3000", text)
        self.assertIn("JFI_NSH=12; JFI_PAR=12", text)
        self.assertIn("cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4", text)
        self.assertIn("cpx62-1743-l3-sb1-scan-basin-force-pool1-recovery-v10", text)
        self.assertIn('"${#JFI_EXCL_LABELS[@]}" -eq 26', text)
        self.assertIn("--fail-on-game-error --enforce-no-book", text)

    def test_pool1_is_two_view_frozen_and_pool2_is_conditional(self):
        p1 = POOL1.read_text(); p2 = POOL2.read_text()
        for seed in ("2026120110", "2026120111"):
            self.assertIn(seed, p1)
        for seed in ("2026120120", "2026120121", "2026120199"):
            self.assertIn(seed, p2)
        self.assertEqual(p1.count("jfi_run_gate "), 2)
        self.assertEqual(p2.count("jfi_run_gate "), 2)
        self.assertIn("POOL2_AUTHORIZED__$AUTHORIZED", p1)
        self.assertIn("POST_POSITIVE_POOL1_AUTHORIZED", p2)
        self.assertIn('--exclude "$IN/pool1-openings.fen"', p2)
        self.assertIn("THIRD_POOL_AUTHORIZED__FALSE", p2)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", p1)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", p2)
        self.assertNotIn("run_match", p1 + p2)


if __name__ == "__main__":
    unittest.main()
