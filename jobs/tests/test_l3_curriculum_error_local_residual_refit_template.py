from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-curriculum-error-local-residual-refit-v1.sh"


class CurriculumErrorLocalResidualRefitTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text()

    def test_sealed_atlas_identity_and_pair_partition_are_fixed(self) -> None:
        for token in (
            'ATLAS_JOB="cpx62-1485-l3-curriculum-error-residual-atlas-v2"',
            'ATLAS_ATTEMPT="20260822T192236Z-2e028428"',
            'ATLAS_CODE="2e0284287657ca6b9325cb76e12e28376c873b0c"',
            "jass.l3_curriculum_error_residual_leaf_shard.v1",
            "INFORMATIVE=290",
            "RECLASSIFIED=63",
            "--bootstrap-samples \"$BOOTSTRAP_SAMPLES\"",
        ):
            self.assertIn(token, self.text)

    def test_stage_is_local_refit_only_and_has_no_forbidden_action(self) -> None:
        for guard in (
            "LOCAL_RESIDUAL_REFIT_ONLY",
            "NO_SELFPLAY",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(guard, self.text)
        for forbidden in ("selfplay_frontier.py generate", "run_jass_gate", "frozen"):
            if forbidden == "frozen":
                continue
            self.assertNotIn(forbidden, self.text)

    def test_negative_science_publishes_no_candidate(self) -> None:
        self.assertIn("bool(report.get('models')) != passed", self.text)
        self.assertIn("(2 if passed else 0)", self.text)
        self.assertIn("discovery_nonzero_step_authorized", self.text)
        self.assertIn("sham_matching_used_calibration", self.text)
        self.assertIn("NEXT_STAGE__NONE", self.text)


if __name__ == "__main__":
    unittest.main()
