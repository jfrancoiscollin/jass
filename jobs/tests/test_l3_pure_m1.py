from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-preflight-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0936-l3-pure-m1-preflight-v1.sh"
TRAIN_TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-train-v1.sh"
TRAIN_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0937-l3-pure-m1-train-v1.sh"
RESUME_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0939-l3-pure-m1-train-resume-v1.sh"
RESUME_V2_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0942-l3-pure-m1-train-resume-v2.sh"
RESUME_V3_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0944-l3-pure-m1-train-resume-v3.sh"
EVAL_TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-eval-v1.sh"
EVAL_WRAPPER = ROOT / "jobs/prepared/l3-pure-maturity-m1-20260724/home-0945-l3-pure-m1-eval-v1.sh"


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
        for script in (TRAIN_TEMPLATE, TRAIN_WRAPPER, RESUME_WRAPPER,
                       RESUME_V2_WRAPPER, RESUME_V3_WRAPPER):
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
        self.assertIn("--optimizer-report", text)
        self.assertIn('if not p.get("success")', text)
        self.assertIn("MAXIT=1000", text)
        self.assertIn("LBFGS_MAXCOR=20", text)
        self.assertIn("LBFGS_GTOL=1e-3", text)
        self.assertIn('--lbfgs-maxcor "$LBFGS_MAXCOR"', text)
        self.assertIn('--lbfgs-gtol "$LBFGS_GTOL"', text)
        self.assertIn("$lower-checkpoint.pjtw.gz", text)
        self.assertIn("M1_TRAINING_SCREEN_READY", text)
        self.assertNotIn("TOP3", text)
        self.assertNotIn("prepare_imbalance2_training.py reweight", text)

    def test_m1_training_wrapper_is_non_promoting(self):
        text = TRAIN_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("home-0937-l3-pure-m1-train-v1", text)
        self.assertIn("ccx33-0790-l3-pure-c0-a-v1", text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)

    def test_resume_reuses_verified_failed_source(self):
        for wrapper in (RESUME_WRAPPER, RESUME_V2_WRAPPER, RESUME_V3_WRAPPER):
            text = wrapper.read_text(encoding="utf-8")
            self.assertIn("home-0937-l3-pure-m1-train-v1/20260724T030013Z-aefecfb1", text)
        template = TRAIN_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("--expected-state failed", template)
        self.assertIn("verified-resume-source.json", template)

    def test_m1_evaluation_contract(self):
        for script in (EVAL_TEMPLATE, EVAL_WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = EVAL_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("MODELS=(F500 F2M R2M)", text)
        self.assertIn("run_gate_group q00 C0", text)
        self.assertIn("run_gate_group native C0", text)
        self.assertIn("run_gate_group q00 GEN2", text)
        self.assertIn("fixed-defender-conversion", text)
        self.assertIn("p1_net p2_moyen p3_mince p4_egal", text)
        self.assertIn("M1_EVALUATION_READY_HUMAN_REVIEW", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)


if __name__ == "__main__":
    unittest.main()
