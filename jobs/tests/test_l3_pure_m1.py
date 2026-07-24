from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-preflight-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0936-l3-pure-m1-preflight-v1.sh"


class M1PreflightContractTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("numpy==1.26.4 scipy==1.14.1", text)
        self.assertIn("M1_PREFLIGHT_READY", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("qs_threat_ext=0,qs_sacs=0", text)
        self.assertIn("--random-open-plies 8", text)
        self.assertIn("--explore-eps 8", text)
        self.assertIn("--pair-openings --drop-plycap", text)
        self.assertIn("--warm-start \"$W/parent.pjtw\"", text)
        self.assertNotIn("TOP3", text)
        self.assertNotIn("reweight", text)

    def test_wrapper_pins_c0_parent_and_stays_prepared(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("ccx33-0790-l3-pure-c0-a-v1", text)
        self.assertIn('${EXPECTED_CODE_SHA:?', text)
        self.assertNotIn("jobs/queue", text)


if __name__ == "__main__":
    unittest.main()
