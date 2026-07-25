from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-repaired-force-review-v1.sh"


class M1RepairedForceReviewContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("MODELS=(F500 F2M R2M)", text)
        self.assertIn("NOPEN=200", text)
        self.assertIn("NSH_GATE=8", text)
        self.assertIn("Q00", text)
        self.assertIn("run_force_wave q00 C0 1", text)
        self.assertIn("run_force_wave q00 GEN2 1", text)
        self.assertIn("run_force_wave native C0 2", text)
        self.assertIn("BASELINE_CODE_SHA", text)
        self.assertIn("git archive \"$BASELINE_CODE_SHA\"", text)
        self.assertIn("l3_bucket_visits.py", text)
        self.assertIn("common.jnnw", text)
        self.assertIn("extra.jnnw", text)
        self.assertIn("hist-g1.jnnw", text)
        self.assertIn("hist-g2.jnnw", text)
        self.assertIn("hist-g3.jnnw", text)
        self.assertIn("M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY", text)
        self.assertIn("CONFIRMATION_AUTHORIZED__FALSE", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_models_and_inputs_are_hash_pinned(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for variable in ("C0_SHA", "F500_SHA", "F2M_SHA", "R2M_SHA"):
            self.assertRegex(text, rf'{variable}="[0-9a-f]{{64}}"')
        self.assertIn("MATRIX_PREFIX", text)
        self.assertIn("M1_PREFIX", text)
        self.assertIn("C0_PREFIX", text)


if __name__ == "__main__":
    unittest.main()
