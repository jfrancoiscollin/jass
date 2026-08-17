import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-primary-pool-gate-v1.sh"


class Context2PrimaryGateTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_native_is_primary_and_q00_is_diagnostic(self) -> None:
        self.assertIn("'primary_view':'native_movetime_0.1'", self.text)
        self.assertIn("'diagnostic_view':'Q00_depth9'", self.text)
        self.assertIn("for view in native q00", self.text)

    def test_uses_paired_fresh_pool_protocol(self) -> None:
        for token in (
            "NOPEN=3000",
            "GAMES_PER_VIEW=6000",
            "BOOTSTRAP=200000",
            "paired_colour_opening_cluster_bootstrap",
            "len(pool.get('disjoint_from',[]))>=10",
            "--pairs 1",
        ):
            self.assertIn(token, self.text)

    def test_authenticates_audit_and_reuses_models(self) -> None:
        self.assertIn("JASS_CONTEXT2_PHASE_TACTICAL_MODELS_AUDITED", self.text)
        self.assertIn("B/C models identical: empty causal gate", self.text)
        self.assertIn("'models_reused':True", self.text)
        self.assertIn("'refits':0", self.text)

    def test_cannot_promote_or_continue(self) -> None:
        self.assertIn("'promotion_authorized':False", self.text)
        self.assertIn("'automatic_next_job':None", self.text)
        self.assertIn("'frozen_cohorts_read':0", self.text)


if __name__ == "__main__":
    unittest.main()
