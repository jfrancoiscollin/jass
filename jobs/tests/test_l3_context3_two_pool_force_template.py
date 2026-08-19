import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context3-two-pool-force-v1.sh"


class Context3TwoPoolForceTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_and_reuses_exact_1418_models(self) -> None:
        for token in (
            "cpx62-1418-l3-context3-paired-patterneval-fit-v1",
            "20260819T074026Z-1e718553",
            "JASS_CONTEXT3_PAIRED_PATTERNEVAL_MODELS_READY",
            "aligned.pjtw.gz",
            "shuffled.pjtw.gz",
            "JASS_CONTEXT3_FORCE_MODELS_AUTHENTICATED",
            "models unexpectedly identical",
            "'reused_without_refit':True",
            "CTX2_INTERVENTION_1409_2M",
            "1418 fit recipe drift",
            "paired target shuffle/marginal drift",
            "paired target causal boundary drift",
        ):
            self.assertIn(token, self.text)

    def test_uses_two_fresh_mutually_disjoint_pools(self) -> None:
        for token in (
            "NOPEN=3000",
            "POOL_SEED_1=2026081907",
            "POOL_SEED_2=2026081908",
            "CANDIDATES=30000",
            "historical exclusion count drift",
            "--exclude \"$ART/ctx3-force-pool1-openings.fen\"",
            "fresh pools overlap",
            "JASS_CONTEXT3_TWO_FRESH_POOLS_READY",
            "'mutually_disjoint':True",
        ):
            self.assertIn(token, self.text)

    def test_native_primary_q00_diagnostic_and_paired_budget(self) -> None:
        for token in (
            "MOVETIME=0.1",
            "FORCE_DEPTH=9",
            "BOOTSTRAP=200000",
            "GAMES_PER_VIEW=6000",
            "--pairs 1",
            "--paired-bootstrap-samples \"$BOOTSTRAP\"",
            "for view in native q00",
            "GAMES_TOTAL__24000",
        ):
            self.assertIn(token, self.text)

    def test_no_refit_selfplay_frozen_or_promotion(self) -> None:
        for marker in (
            "MODELS_REUSED__TRUE",
            "REFITS__0",
            "NEW_SELFPLAY__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(marker, self.text)
        self.assertNotRegex(self.text, re.compile(r"frozen_test|--selfplay|--fit-pattern", re.I))


if __name__ == "__main__":
    unittest.main()
