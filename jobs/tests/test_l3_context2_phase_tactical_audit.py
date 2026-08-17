import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-phase-tactical-audit-v1.sh"


class Context2PhaseTacticalAuditTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_immutable_fit_and_reused_ctx1(self) -> None:
        self.assertIn("home-1373-l3-context2-phase-tactical-fit-v1", self.text)
        self.assertIn("20260816T214312Z-9e224d6e", self.text)
        self.assertIn("cpx62-1340-jass-megacorpus-comparative-fit-v1", self.text)
        self.assertIn("A: CTX1 reuse drift", self.text)

    def test_audits_strict_context2_causal_contract(self) -> None:
        for token in (
            "ctx2-phase-tactical-30",
            "opening_id",
            "game_equal",
            "terminal_wdl_black_x_tempo_phase_4_bins",
            "target marginals drift",
            "symmetry_contract_tests_passed",
        ):
            self.assertIn(token, self.text)

    def test_cannot_promote_or_continue(self) -> None:
        self.assertIn("strength_games_played':0", self.text)
        self.assertIn("frozen_cohorts_read':0", self.text)
        self.assertIn("promotion_authorized':False", self.text)
        self.assertIn("automatic_next_job':None", self.text)


if __name__ == "__main__":
    unittest.main()
