import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REFIT = (ROOT / "jobs/templates/l3-hier-l2-refit-v1.sh").read_text(encoding="utf-8")
READOUT = (ROOT / "jobs/templates/l3-hier-l2-readout-v1.sh").read_text(encoding="utf-8")


class HierL2RefitTemplateTest(unittest.TestCase):
    def test_fixed_one_factor_contract(self):
        self.assertIn("HIER_CONTROL=0; HIER_CANDIDATE=3e-5", REFIT)
        self.assertIn('L2=3e-5', REFIT)
        self.assertIn('LBFGS_GTOL=1e-4', REFIT)
        self.assertIn('MAX_GRAD_INF=1e-4', REFIT)
        self.assertIn('grad > limit', REFIT)
        self.assertIn('"all_arms_pass": True', REFIT)
        self.assertIn('l3_optimizer_pair_guard.py', REFIT)
        self.assertIn('--edge-high 0.8 --edge-low 0.6', REFIT)
        self.assertIn('--iteration-ratio-limit 5', REFIT)
        self.assertIn('optimizer-pair-guard.json', REFIT)
        self.assertIn('diff != ["hier_l2"]', REFIT)
        self.assertEqual(REFIT.count('fit_arm control "$HIER_CONTROL"'), 1)
        self.assertEqual(REFIT.count('fit_arm hier "$HIER_CANDIDATE"'), 1)
        self.assertNotRegex(REFIT, r"ARM_[AB]|HIER_(CONTROL|CANDIDATE)=\"\$\{")

    def test_every_consumed_scientific_input_has_a_producer(self):
        self.assertIn("home-0977-l3-pure-turnover1to1-train-v1", REFIT)
        self.assertIn("work/m2.fit.jnnw=corpus.jnnw", REFIT)
        self.assertIn("work/parent-f2m.pjtw=parent.pjtw", REFIT)
        self.assertIn("artefacts/m2-split.json=split.json", REFIT)
        self.assertIn("--dump-eval-features", REFIT)
        self.assertIn('EXPECTED_EXTRAS=120', REFIT)

    def test_optimizer_keys_are_written_by_tool_and_read_by_template(self):
        trainer = (ROOT / "pattern_jass/tools/train.py").read_text(encoding="utf-8")
        for key in (
            "success", "status", "message", "iterations",
            "function_evaluations", "gradient_inf_norm", "gtol",
        ):
            self.assertIn(f'"{key}"', trainer)
            self.assertIn(f'"{key}"', REFIT)

    def test_scope_guards_and_no_inflight_template_mutation(self):
        self.assertIn("home/codex/hier-l2-refit/at-sha", REFIT)
        self.assertIn("FULL_RUN_APPROVED", REFIT)
        self.assertIn("SCIENTIFIC_GO", REFIT)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", REFIT)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", REFIT)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", REFIT)
        self.assertNotRegex(
            REFIT,
            r"l3-exact-fold-refit-v1\.sh|l3-model-gate-v1\.sh|l3-succession-guards-v1\.sh",
        )


class HierL2ReadoutTemplateTest(unittest.TestCase):
    def test_readout_is_immutable_and_compute_free(self):
        self.assertIn("SOURCE_RESULT_URI", READOUT)
        self.assertIn("EXPECTED_SOURCE_ATTEMPT", READOUT)
        self.assertIn("fetch_result_files.py", READOUT)
        self.assertIn("l3_hier_l2_verdict.py", READOUT)
        self.assertNotRegex(READOUT, r"cmake|run_jass_gate|train_stream|--pairs")

    def test_no_promotion_or_continuation(self):
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", READOUT)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", READOUT)
        self.assertIn("home/codex/hier-l2-readout/at-sha", READOUT)


if __name__ == "__main__":
    unittest.main()
