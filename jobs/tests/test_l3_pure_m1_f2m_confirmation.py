from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-f2m-confirmation-v1.sh"


class M1F2MConfirmationContractTests(unittest.TestCase):
    def test_shell_and_confirmation_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("NOPEN=500", text)
        self.assertIn("NSH_GATE=16", text)
        self.assertIn("OPENING_SEED=173205", text)
        self.assertIn("--gen-opening-pool", text)
        self.assertIn("--exclude data/dilf_combinations.fen", text)
        self.assertIn("--expected \"$NOPEN\"", text)
        self.assertIn("run_wave q00 4", text)
        self.assertIn("run_wave native 4", text)
        self.assertIn("F2M.pjtw", text)
        self.assertIn("C0.pjtw", text)
        self.assertIn("R2M.pjtw", text)
        self.assertIn("l3_f2m_independent_confirmation.py", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_inputs_are_immutable_and_hash_pinned(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for variable in ("C0_SHA", "F2M_SHA", "R2M_SHA"):
            self.assertRegex(text, rf'{variable}="[0-9a-f]{{64}}"')
        self.assertIn("MATRIX_PREFIX", text)
        self.assertIn("REVIEW_PREFIX", text)
        self.assertIn("M1_PREFIX", text)


if __name__ == "__main__":
    unittest.main()
