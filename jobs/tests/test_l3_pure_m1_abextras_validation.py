from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-abextras-validation-v1.sh"


class M1ABExtrasValidationContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("GEN_SEED=950027", text)
        self.assertIn("TARGET_PER_STRATUM=300", text)
        self.assertIn("--player-pattern \"$W/C0.pjtw\"", text)
        self.assertIn("--val-margin-max 1", text)
        self.assertIn("--thermo \"$IN/gauge.fen\"", text)
        self.assertIn("--required-strata p3_mince p4_egal", text)
        self.assertIn("MODELS=(C0 F500 AB_EXTRAS)", text)
        self.assertIn("run_force q00 C0", text)
        self.assertIn("run_force native C0", text)
        self.assertIn("run_force q00 GEN2", text)
        self.assertIn("confirmed_recovery", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_candidate_and_inputs_are_immutable(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("c86da4bd7ce2d2cb9e1b73ccec9785a770d4727c51b875a03fe9e6edd865ba94", text)
        self.assertIn("work/AB_EXTRAS.pjtw=ab-extras.pjtw", text)
        self.assertIn("blind_to_candidates", text)
        self.assertIn("old_gauge_excluded", text)


if __name__ == "__main__":
    unittest.main()
