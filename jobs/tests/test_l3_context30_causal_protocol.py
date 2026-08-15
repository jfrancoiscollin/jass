"""Static contracts for the full-Jass CONTEXT_30 causal protocol."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "experiments" / "L3_CONTEXT30_CAUSAL_GATE_PREREGISTRATION_20260816.md"
GATE = ROOT / "jobs" / "templates" / "l3-model-gate-v1.sh"


class Context30CausalProtocolTest(unittest.TestCase):
    def test_three_hierarchical_contrasts_and_no_elo_floor(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("ALIGNED − SHUFFLED", text)
        self.assertIn("ALIGNED − OUTCOME", text)
        self.assertIn("ALIGNED − L2LOW", text)
        self.assertLess(text.index("ALIGNED − SHUFFLED"), text.index("ALIGNED − OUTCOME"))
        self.assertLess(text.index("ALIGNED − OUTCOME"), text.index("ALIGNED − L2LOW"))
        self.assertIn("aucun seuil Elo minimal", text)
        self.assertIn("P(Elo > 0) > 95 %", text)

    def test_two_fresh_disjoint_pools_are_preregistered(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("C30_POOL_1 seed=2026081601", text)
        self.assertIn("C30_POOL_2 seed=2026081602", text)
        self.assertIn("disjoint du premier", text)
        self.assertIn("24 000 parties par contraste", text)
        self.assertIn("seed=20260816", text)
        self.assertIn("MAX_ERROR_RATE=0.02", text)

    def test_gate_exposes_paired_bootstrap_and_error_cap(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        self.assertIn("PAIRED_BOOTSTRAP_SAMPLES", text)
        self.assertIn("--paired-bootstrap-samples", text)
        self.assertIn("--paired-bootstrap-seed", text)
        self.assertIn("MAX_ERROR_RATE", text)
        self.assertIn("error_draws", text)
        self.assertIn("error_guard_passed", text)

    def test_no_automatic_science_transition(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Aucun job enfant", text)
        self.assertIn("ni promotion ni continuation automatique", text)
