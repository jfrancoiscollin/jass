from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-preflight-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0936-l3-pure-m1-preflight-v1.sh"
TRAIN_TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-train-v1.sh"
TRAIN_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0937-l3-pure-m1-train-v1.sh"


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

    def test_m1_three_arm_training_contract(self):
        for script in (TRAIN_TEMPLATE, TRAIN_WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = TRAIN_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("COMMON_RECORDS=500000", text)
        self.assertIn("EXTRA_RECORDS=1500000", text)
        self.assertIn("PRODUCERS=12", text)
        self.assertIn("fit_arm F500 f500", text)
        self.assertIn("fit_arm F2M f2m", text)
        self.assertIn("fit_arm R2M r2m", text)
        self.assertIn('"$W/common.raw.jnnw" "$W/common.raw.jsm"', text)
        self.assertIn('"$W/hist-g1.jnnw" "$W/hist-g1.jsm"', text)
        self.assertIn('"$W/hist-g2.jnnw" "$W/hist-g2.jsm"', text)
        self.assertIn('"$W/hist-g3.jnnw" "$W/hist-g3.jsm"', text)
        self.assertEqual(text.count("--renamespace-nested"), 3)
        self.assertIn("--warm-start \"$W/parent.pjtw\"", text)
        self.assertIn('[ "$iters" -lt "$MAXIT" ]', text)
        self.assertIn("M1_TRAINING_SCREEN_READY", text)
        self.assertNotIn("TOP3", text)
        self.assertNotIn("prepare_imbalance2_training.py reweight", text)

    def test_m1_training_wrapper_is_non_promoting(self):
        text = TRAIN_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("home-0937-l3-pure-m1-train-v1", text)
        self.assertIn("ccx33-0790-l3-pure-c0-a-v1", text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)


if __name__ == "__main__":
    unittest.main()
