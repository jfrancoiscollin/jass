from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-train-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-m2-20260725"
    / "home-0966-l3-pure-m2-f2m-fresh2m-train-v1.sh"
)


class M2TrainingContractTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_fresh_two_million_from_f2m(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("TOTAL_RECORDS=2000000", text)
        self.assertIn("PRODUCERS=12", text)
        self.assertIn("BASE_SEED=1618033", text)
        self.assertIn('--nnue "$W/parent-f2m.pjtw"', text)
        self.assertIn("--wdl-zero-score", text)
        self.assertIn("--random-open-plies 8", text)
        self.assertIn("--explore-eps 8", text)
        self.assertIn("--pair-openings --drop-plycap", text)
        self.assertIn("historical_replay_records", text)
        self.assertNotIn("hist-g1", text)
        self.assertIn('"role_reweight_v2": False', text)
        self.assertNotIn("prepare_imbalance2_training.py reweight", text)
        self.assertNotIn("TOP3", text)

    def test_fit_is_reproducible_and_recoverable(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("numpy==1.26.4 scipy==1.14.1", text)
        self.assertIn("--warm-start \"$W/parent-f2m.pjtw\"", text)
        self.assertIn("--target wdl --loss logistic --color-fold --tempo-stage", text)
        self.assertIn("MAXIT=1000", text)
        self.assertIn("LBFGS_MAXCOR=20", text)
        self.assertIn("LBFGS_GTOL=1e-3", text)
        self.assertIn("m2-fresh-2m.jnnw.gz", text)
        self.assertIn("m2-fresh-2m.jsm.gz", text)
        self.assertLess(
            text.index('m2-fresh-2m.jnnw.gz'),
            text.index("phase split-by-opening-and-fit"),
        )
        self.assertIn("m2-checkpoint.pjtw.gz", text)
        self.assertIn('if not json.load(open(sys.argv[1])).get("success")', text)

    def test_parent_and_nonpromotion_guards(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW", text)
        self.assertIn("recommended_general_champion", text)
        self.assertIn("EXPECTED_PARENT_MODEL_SHA256", text)
        self.assertIn("M2_TRAINING_SCREEN_READY", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("automatic_next_job", text)
        self.assertIn("home-0944-l3-pure-m1-train-resume-v3", wrapper)
        self.assertIn("home-0965-l3-pure-f2m-gen2-repaired-benchmark-v1", wrapper)
        self.assertIn("NO_AUTOMATIC_CONTINUATION=1", wrapper)

    def test_repaired_engine_witnesses_and_tests(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("ctest --test-dir", text)
        self.assertIn("W:W40,43,K2:B8,18,29,30", text)
        self.assertIn("B:W13,23,25:B6,14,24,K45", text)


if __name__ == "__main__":
    unittest.main()
