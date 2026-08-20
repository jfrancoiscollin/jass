#!/usr/bin/env python3
import subprocess
import unittest
from pathlib import Path


class ExploratoryFresh2MTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = Path(
            "jobs/templates/l3-context2-intervention-corpus-fresh2m-exploratory-v2.sh"
        )
        cls.text = cls.path.read_text(encoding="utf-8")

    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(self.path)], check=True)

    def test_pins_certified_1409_recipe_blob(self) -> None:
        self.assertIn(
            'EXPECTED_BASE_BLOB="3b52e23f2de4e526347a22fe68a280d48107be31"',
            self.text,
        )
        self.assertIn("l3-context2-intervention-corpus-v1.sh", self.text)
        self.assertIn("certified 1409 corpus template blob drift", self.text)

    def test_only_scientific_generation_change_is_fresh_seed(self) -> None:
        self.assertIn("OLD_SEED=2026081805", self.text)
        self.assertIn("NEW_SEED=2026082105", self.text)
        self.assertIn(
            '"scientific_generation_changes": ["fresh_seed"]', self.text
        )
        self.assertIn("unexpected substitution count", self.text)
        self.assertIn("if len(changes) != 5", self.text)

    def test_six_cell_quotas_remain_locked(self) -> None:
        for token in (
            "BASE 300000 8 8 60 0 0 8",
            "ROP16 600000 16 8 60 0 0 8",
            "EPS16 500000 8 16 60 0 0 8",
            "DECAY120 100000 8 8 120 0 0 8",
            "TOPK3M30 100000 8 8 60 3 30 8",
            "DEPTH10 400000 8 8 60 0 0 10",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_exploratory_scope_cannot_rehabilitate_ctx4(self) -> None:
        self.assertIn("EXPLORATORY_POST_CTX4", self.text)
        self.assertIn("JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED", self.text)
        self.assertIn('"ctx4_verdict_reopened": False', self.text)
        self.assertIn("CONFIRMATORY_CLAIM_AUTHORIZED__FALSE", self.text)
        self.assertIn('"issue": 544', self.text)

    def test_terminal_artifact_contract(self) -> None:
        self.assertIn("JASS_EXPLORATORY_FRESH2M_D2_READY", self.text)
        self.assertIn("D2_FRESH_2M", self.text)
        self.assertIn("native_JNNW_WDL_identical_for_D1_and_D2", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertIn("exec bash \"$PATCHED\"", self.text)


if __name__ == "__main__":
    unittest.main()
