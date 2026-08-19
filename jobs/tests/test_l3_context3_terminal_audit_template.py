import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context3-terminal-audit-v1.sh"


class Context3TerminalAuditTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_exact_1419_attempt_and_all_raw_evidence(self) -> None:
        for token in (
            "cpx62-1419-l3-context3-two-pool-force-v1",
            "20260819T112556Z-8adc506a",
            "8adc506a8ec95b1f170bc706def1fe052eca0d98",
            "pool1-native.json",
            "pool1-q00.json",
            "pool2-native.json",
            "pool2-q00.json",
            "verified-source-1419.json",
            "result_state",
            "exit_code",
        ):
            self.assertIn(token, self.text)

    def test_recomputes_and_requires_exact_readout_equality(self) -> None:
        for token in (
            "l3_context3_two_pool_force_readout.py",
            "--bootstrap-samples 200000",
            "--combined-native-seed 2026081911",
            "--combined-q00-seed 2026081912",
            "source==recomputed",
            "raw_readout_recomputed_exactly",
            "RAW_READOUT_RECOMPUTED_EXACTLY__TRUE",
        ):
            self.assertIn(token, self.text)

    def test_publishes_complete_visible_metrics_and_classification(self) -> None:
        for token in (
            "_WDL__",
            "_RATE__",
            "_CI95__",
            "_ERROR_DRAWS__",
            "('NATIVE',native)",
            "('Q00',q00)",
            "{label}_COMBINED_RATE__",
            "{label}_COMBINED_CI95__",
            "{label}_COMBINED_P_GT_HALF__",
            "{label}_INTER_POOL_Z__",
            "CLASSIFICATION__",
            "JASS_CONTEXT3_TERMINAL_AUDIT_READY",
        ):
            self.assertIn(token, self.text)

    def test_is_strictly_read_only_scientifically(self) -> None:
        for marker in (
            "SOURCE_GAMES_AUDITED__24000",
            "GAMES_REPLAYED__0",
            "REFITS__0",
            "NEW_SELFPLAY__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(marker, self.text)
        self.assertNotRegex(
            self.text,
            re.compile(r"frozen_test|--selfplay|--fit-pattern|run_jass_gate_bounded", re.I),
        )


if __name__ == "__main__":
    unittest.main()
