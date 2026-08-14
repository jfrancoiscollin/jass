from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs" / "templates" / "jass-megacorpus-smoke-fit-v1.sh").read_text()


class MegaCorpusSmokeTemplateTest(unittest.TestCase):
    def test_authenticates_source_and_parent(self):
        self.assertIn("jobs/tools/fetch_result_files.py", TEXT)
        self.assertIn("L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY", TEXT)
        self.assertIn("data_raw_sha256", TEXT)
        self.assertIn("meta_raw_sha256", TEXT)
        self.assertIn("L2LOW_SHA", TEXT)

    def test_game_aware_provenance_and_context_contract(self):
        self.assertIn("jass_megacorpus_materialize.py", TEXT)
        self.assertIn("origin_source_id.npy", TEXT)
        self.assertIn("origin_record_index.npy", TEXT)
        self.assertIn("l3_conditional_targets.py", TEXT)
        self.assertIn("--target external", TEXT)
        self.assertIn("--prior-mean \"$W/l2low.pjtw\" --prior-decay 0", TEXT)
        self.assertIn("--max-iter \"$MAXIT\"", TEXT)

    def test_cpx_runtime_is_versioned_persistent_and_never_installs_torch(self):
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", TEXT)
        self.assertIn(".jass-runtime-ready-v1", TEXT)
        self.assertIn("python3 -m venv --clear", TEXT)
        self.assertIn("numpy scipy >\"$W/pip-bootstrap-once.log\"", TEXT)
        self.assertNotIn("numpy==1.26.4", TEXT)
        self.assertNotIn("pip install torch", TEXT)
        self.assertIn("pytorch_installed_or_required':False", TEXT)

    def test_no_frozen_strength_or_automatic_promotion(self):
        lowered = TEXT.lower()
        self.assertNotIn("frozen_test", lowered)
        self.assertIn("frozen_cohorts_read':0", TEXT)
        self.assertIn("scientific_strength_verdict':None", TEXT)
        self.assertIn("promotion_authorized':False", TEXT)
        self.assertIn("automatic_next_job':None", TEXT)


if __name__ == "__main__":
    unittest.main()
