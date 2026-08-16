"""Fail-closed contracts for the full-Jass CONTEXT_30 causal control fit."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context30-causal-fit-v1.sh"


def _script() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


class Context30CausalFitTemplateTest(unittest.TestCase):
    def test_reuses_certified_aligned_arm_and_immutable_current_corpus(self) -> None:
        script = _script()
        self.assertIn("cpx62-1340-jass-megacorpus-comparative-fit-v1", script)
        self.assertIn("cpx62-1341-jass-megacorpus-arm-d-fit-v1", script)
        self.assertIn("home-0977-l3-pure-turnover1to1-train-v1", script)
        self.assertIn("cpx62-1164-l3-prior-dose-l2-refit-v1", script)
        self.assertIn("current_2m.pjtw.gz=aligned.pjtw.gz", script)
        self.assertIn("source-A-convergence.json", script)
        self.assertNotIn("generate-selfplay", script)
        self.assertIn("frozen_cohorts_read':0", script)

    def test_reconstructs_aligned_and_builds_stronger_shuffled_control(self) -> None:
        script = _script()
        self.assertIn("jobs/tools/l3_conditional_targets.py", script)
        self.assertIn("--aligned-out", script)
        self.assertIn("--shuffled-out", script)
        self.assertIn("reconstructed aligned target differs from source", script)
        self.assertIn("--shuffle-within-wdl", script)
        self.assertIn("all_cohort_fold_marginals_preserved", script)
        self.assertIn("all_final_target_marginals_preserved", script)
        self.assertIn("terminal_wdl_black", script)
        self.assertIn("fixed_point_count", script)
        self.assertIn("aligned source model consumed another target", script)
        self.assertIn('"$ART/conditional-targets.json" "$EXPECTED_CODE_SHA"', script)

    def test_new_controls_change_only_target_channel(self) -> None:
        script = _script()
        for flag in (
            "--exact-fold",
            "--tempo-stage",
            "--prior-mean",
            "--prior-decay 0",
            "--l2 1e-5",
            "--lbfgs-gtol 1e-4",
            "--lbfgs-maxcor 20",
        ):
            self.assertIn(flag, script)
        self.assertIn("fit_control shuffled --target external", script)
        self.assertIn("fit_control outcome --target wdl", script)
        self.assertIn("sequential-contention-free-control-fits", script)
        self.assertLess(script.index("fit_control shuffled"), script.index("fit_control outcome"))

    def test_every_model_is_convergence_and_architecture_certified(self) -> None:
        script = _script()
        self.assertGreaterEqual(script.count("jobs/tools/verify_optimizer_convergence.py"), 3)
        self.assertIn("aligned-source-convergence-recheck.json", script)
        self.assertIn("--expected-gtol 1e-4", script)
        self.assertIn("n_pat!=4251528", script)
        self.assertIn("n_ext!=120", script)
        self.assertIn("causal arms are not three distinct models", script)
        self.assertIn("Path(p).stat().st_size!=expected", script)

    def test_source_code_contract_uses_sealed_blob_ids(self) -> None:
        script = _script()
        self.assertIn('TARGET_BUILDER_BLOB="968b253', script)
        self.assertIn('TRAIN_STREAM_BLOB="12ed5f0', script)
        self.assertIn('SPLITTER_BLOB="2147a14', script)
        self.assertNotIn('git rev-parse "$ALIGNED_CODE_SHA:', script)

    def test_runtime_is_persistent_and_matches_aligned_source(self) -> None:
        script = _script()
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", script)
        self.assertIn("VENV_READY", script)
        self.assertIn("numeric stack differs from aligned fit", script)
        self.assertIn("pytorch_installed_or_required':False", script)
        self.assertNotIn("jobs.tests.test_l3_conditional_targets", script)

    def test_split_reproduction_uses_real_manifest_schema_and_source_hashes(self) -> None:
        script = _script()
        self.assertIn("if current != source:", script)
        self.assertIn("split manifest drift", script)
        self.assertIn('targets[\'source\'][key]', script)
        self.assertIn("split {label} hash drift", script)
        self.assertIn('"$IN/source-targets.json"', script)
        self.assertIn('"$W/current.jnnw" "$W/current.jsm"', script)
        self.assertNotIn("a['files'][key]", script)

    def test_fit_cannot_promote_or_continue_automatically(self) -> None:
        script = _script()
        self.assertIn("JASS_CONTEXT30_CAUSAL_MODELS_READY", script)
        self.assertIn("strength_games_played':0", script)
        self.assertIn("promotion_authorized':False", script)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", script)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", script)
