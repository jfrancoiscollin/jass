import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-reverse-seed-scale-diagnostic-v1.sh"


class ReverseSeedScaleDiagnosticTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_is_read_only_compute(self):
        forbidden = ("--gen-data-wdl", "train_stream.py", "rank_finetune.py", "jass_vs_jass")
        for token in forbidden:
            self.assertNotIn(token, self.text)
        self.assertIn("self_play_games_generated", (ROOT / "jobs/tools/l3_reverse_seed_scale_diagnostic.py").read_text(encoding="utf-8"))

    def test_authenticates_all_sources_and_models(self):
        for token in (
            "STAGE2_PREFIX", "READOUT2_PREFIX", "STAGE4_PREFIX", "READOUT4_PREFIX",
            "PARENT_PREFIX", "STAGE2_CONTROL_SHA", "STAGE2_TREATMENT_SHA",
            "STAGE4_CONTROL_SHA", "STAGE4_TREATMENT_SHA",
        ):
            self.assertIn(token, self.text)

    def test_terminal_guards(self):
        self.assertIn("SCIENTIFIC_RESULT__FALSE", self.text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", self.text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", self.text)
        self.assertIn("L3_PURE_REVERSE_SEED_SCALE_DIAGNOSTIC_COMPLETE", self.text)


if __name__ == "__main__":
    unittest.main()
