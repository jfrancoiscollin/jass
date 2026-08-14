from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (
    ROOT / "jobs" / "templates" / "jass-megacorpus-comparative-fit-v1.sh"
).read_text(encoding="utf-8")


class MegaCorpusComparativeTemplateTest(unittest.TestCase):
    def test_three_pre_registered_arms_and_nested_sampling(self):
        self.assertIn("CURRENT_2M", TEXT)
        self.assertIn("MEGA_EQ_2M", TEXT)
        self.assertIn("MEGA_FULL_4M", TEXT)
        self.assertIn("make_mega_arm mega_eq_2m 20", TEXT)
        self.assertIn("make_mega_arm mega_full_4m 10", TEXT)
        self.assertIn("B_is_record_subset_of_C", TEXT)

    def test_same_architecture_target_and_optimizer_recipe(self):
        self.assertIn("l3_conditional_targets.py", TEXT)
        self.assertIn("for arm in current_2m mega_eq_2m mega_full_4m", TEXT)
        self.assertIn('--prior-mean "$W/l2low.pjtw" --prior-decay 0', TEXT)
        self.assertIn("--exact-fold --tempo-stage", TEXT)
        self.assertIn('--max-iter "$MAXIT"', TEXT)
        self.assertIn("MAXIT=2000", TEXT)

    def test_sources_are_immutable_and_authenticated(self):
        self.assertIn("home-0977-l3-pure-turnover1to1-train-v1", TEXT)
        self.assertIn("home-1044-l3-pure-hard-replay-large-source-v1", TEXT)
        self.assertIn("cpx62-1164-l3-prior-dose-l2-refit-v1", TEXT)
        self.assertIn("TURNOVER_CORPUS_SHA", TEXT)
        self.assertIn("data_raw_sha256", TEXT)
        self.assertIn("L2LOW_SHA", TEXT)

    def test_no_strength_frozen_promotion_or_automatic_child(self):
        lowered = TEXT.lower()
        self.assertNotIn("frozen_test", lowered)
        self.assertIn("frozen_cohorts_read':0", TEXT)
        self.assertIn("scientific_strength_verdict':None", TEXT)
        self.assertIn("promotion_authorized':False", TEXT)
        self.assertIn("automatic_next_job':None", TEXT)

    def test_persistent_runtime_does_not_install_torch(self):
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", TEXT)
        self.assertIn("pytorch_installed_or_required':False", TEXT)
        self.assertNotIn("pip install torch", TEXT)

    def test_shell_parameter_expansions_are_not_pid_prefixed(self):
        self.assertNotIn("$${", TEXT)
        self.assertIn("${SCIENTIFIC_GO:-0}", TEXT)


if __name__ == "__main__":
    unittest.main()
