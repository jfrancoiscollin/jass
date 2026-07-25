from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-eval-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-d10-causal-20260726"
    / "home-0972-l3-pure-d10-causal-independent-eval-v1.sh"
)


class D10CausalEvaluationJobTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_three_way_force_contract(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("D10_CAUSAL)", text)
        self.assertIn('CANDIDATE_LABEL=D10', text)
        self.assertIn("run_gate q00 M2", text)
        self.assertIn("run_gate native M2", text)
        self.assertIn('force-$view-$CANDIDATE_LABEL-vs-$opponent.json', text)
        self.assertIn('OPENING_SEED" != 244949', text)

    def test_prior_m2_pool_is_reconstructed_and_excluded(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("prior-m2-candidates.fen", text)
        self.assertIn("M2_INDEPENDENT_OPENINGS_SHA", text)
        self.assertIn('--exclude "$W/prior-m2-independent.fen"', text)
        self.assertIn("reconstructed M2 independent opening pool hash drift", text)

    def test_exact_corpora_and_conversion_controls(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("d8-m2.jnnw.gz", text)
        self.assertIn("D8_M2_CORPUS_SHA", text)
        self.assertIn("D10-coverage.json", text.replace("$CANDIDATE_LABEL", "D10"))
        self.assertIn("M2-p3_mince.json", text)
        self.assertIn("M2-p4_egal.json", text)
        self.assertIn("l3_d10_causal_evaluation.py", text)

    def test_nonpromotion_is_preserved(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_wrapper_pins_sources_but_waits_for_training_hashes(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("home-0971-l3-pure-d10-causal-fresh2m-train-v1", text)
        self.assertIn("home-0970bis-l3-pure-m2-independent-eval-v3", text)
        self.assertIn("EXPECTED_CANDIDATE_MODEL_SHA256", text)
        self.assertIn("EXPECTED_CANDIDATE_CORPUS_SHA256", text)
        self.assertIn("OPENING_SEED_OVERRIDE=314159", text)


if __name__ == "__main__":
    unittest.main()
