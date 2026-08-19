from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context3-decision-flip-autopsy-v1.sh"


class DecisionFlipAutopsyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_pins_certified_sources(self) -> None:
        for value in (
            "cpx62-1418-l3-context3-paired-patterneval-fit-v1",
            "20260819T074026Z-1e718553",
            "cpx62-1419-l3-context3-two-pool-force-v1",
            "20260819T112556Z-8adc506a",
            "cpx62-1420-l3-context3-terminal-audit-v1",
            "20260819T134046Z-69170897",
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        ):
            self.assertIn(value, self.text)

    def test_read_only_scope_and_sizing_are_explicit(self) -> None:
        for value in (
            "PER_POOL=192",
            "TOTAL=384",
            "NSH=8",
            "CHOICE_DEPTH=9",
            "JUDGE_DEPTH=12",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "SELFPLAY__0",
            "PATTERNEVAL_FITS__0",
            "STRENGTH_GAMES__0",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(value, self.text)

    def test_parallel_wait_uses_only_worker_pids(self) -> None:
        self.assertIn('pids+=("$!")', self.text)
        self.assertIn('for pid in "${pids[@]}"; do wait "$pid"', self.text)
        self.assertNotIn("\nwait\n", self.text)

    def test_persistent_numeric_runtime_is_reused(self) -> None:
        self.assertIn(".jass-runtime-ready-v1", self.text)
        self.assertNotIn("pip install", self.text)
        self.assertNotIn("python3 -m venv", self.text)


if __name__ == "__main__":
    unittest.main()
