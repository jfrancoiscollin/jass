"""Static contracts for the DCR1 mechanistic job template."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-decision-ranker-mechanism-screen-v1.sh"


class DecisionRankerTemplateTest(unittest.TestCase):
    def test_bash_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(TEMPLATE)], cwd=ROOT, check=True)

    def test_preregistered_science_is_locked(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        required = (
            "SOURCE_CONTEXT30_ROOT",
            "EXPECTED_CONTEXT30_JOB",
            "EXPECTED_CONTEXT30_ATTEMPT",
            "EXPECTED_CONTEXT30_CODE_SHA",
            "PASS_VERDICT=\"JASS_DECISION_RANKER_MECHANISM_SCREEN_PASSED\"",
            "FAIL_VERDICT=\"JASS_DECISION_RANKER_MECHANISM_SCREEN_FAILED\"",
            "PER_POOL=512",
            "CHOICE_DEPTH=9",
            "AUDIT_DEPTH=12",
            "JUDGE_DEPTH=14",
            "UNCERTAINTY_CP=40",
            "JUDGE_DEADBAND_CP=8",
            "FOLDS=5",
            "RIDGE=0.1",
            "TARGET_CLIP_CP=200",
            "BOOTSTRAP=100000",
            "MIN_TOTAL=240",
            "MIN_PER_POOL=80",
            "MIN_POSITIVE=30",
            "MIN_NEGATIVE=120",
            "MIN_STABLE_FRACTION=0.65",
            "MIN_INTERVENTIONS=20",
            "MAX_INTERVENTION_RATE=0.35",
            "--dump-conditional-context-v2",
            "l3_decision_ranker_screen.py worker",
            "l3_decision_ranker_screen.py aggregate",
            "PATTERNEVAL_FITS_RUN__0",
            "RANKER_FITS_RUN__6",
            "NEW_SELFPLAY__0",
            "STRENGTH_GAMES_PLAYED__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
            "SCAN_LABELS_READ__0",
            "CURRICULUM_SCALAR_UNCHANGED__TRUE",
        )
        for token in required:
            self.assertIn(token, text)

    def test_mechanistic_phase_contains_no_deployment_or_force_path(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        forbidden = (
            "run_jass_gate_bounded.py",
            "--gen-selfplay",
            "train_stream.py",
            "train_stream_exact.py",
            "rank_finetune.py",
            "PROMOTION_AUTHORIZED__TRUE",
            "NEXT_STAGE_AUTHORIZED__TRUE\"",  # no unconditional marker
        )
        for token in forbidden:
            self.assertNotIn(token, text)
        self.assertIn("source_pool_results_used_as_labels':False", text)
        self.assertIn("automatic_next_job']=None", text)

    def test_source_pools_are_terminal_context30_and_not_regenerated(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "replay-context30-target-pool1-openings.fen=pool1.fen", text
        )
        self.assertIn(
            "replay-context30-target-pool2-openings.fen=pool2.fen", text
        )
        self.assertNotIn("--gen-opening-pool", text)
        self.assertIn("historical_exclusion_count')!=23", text)
        self.assertIn("source_job,attempt,code", text)
        self.assertNotIn("EXPECTED_1455_ATTEMPT", text)
        doc = (
            ROOT
            / "docs"
            / "experiments"
            / "L3_DECISION_RANKER_MECHANISM_SCREEN_20260822.md"
        ).read_text(encoding="utf-8")
        self.assertIn("La sélection ignore tous les résultats", doc)
        self.assertIn("définitivement interdits à tout futur gate de force", doc)


if __name__ == "__main__":
    unittest.main()
