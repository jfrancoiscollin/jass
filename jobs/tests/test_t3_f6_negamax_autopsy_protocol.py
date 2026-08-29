#!/usr/bin/env python3
"""Static guards for the post-terminal, read-only negamax autopsy."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/t3_f6_negamax_autopsy.cpp"
TEMPLATE = ROOT / "jobs/templates/l3-t3-f6-negamax-autopsy-v1.sh"
DOC = ROOT / "docs/experiments/L3_T3_F6_NEGAMAX_AUTOPSY_20260829.md"


class NegamaxAutopsyProtocolTests(unittest.TestCase):
    def test_tool_freezes_exact_source_and_classification_set(self) -> None:
        text = TOOL.read_text(encoding="utf-8")
        for token in (
            "cpx62-1648-l3-t3-f6-runtime-r0-v2",
            "20260829T132226Z-f559baed",
            "R0_V2_OBSERVED_T3_SCORE = -51",
            'run_arm("T0"',
            'run_arm("T3"',
            "_DIRECT_NEGAMAX_PASS",
            "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH",
            "T3_RUNTIME_POV_INTEGRATION_DEFECT",
            "NEGAMAX_MISMATCH_UNRESOLVED",
            "strength_games",
        ):
            self.assertIn(token, text)

    def test_runner_is_diagnostic_only(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for token in (
            'cpx62-1650-l3-t3-f6-negamax-autopsy-v1',
            't3_f6_negamax_autopsy',
            'R0-v2 score not reproduced',
            'STRENGTH_GAMES__0',
            'FORCE_AUTHORIZED__FALSE',
            'V3_EXECUTED__FALSE',
        ):
            self.assertIn(token, text)
        for forbidden in ("--movetime 0.1", "--depth 9", "jass_vs_jass", "POOL1"):
            self.assertNotIn(forbidden, text)

    def test_document_preserves_terminal_and_scope(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        for token in (
            "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED",
            "diagnostic post-terminal",
            "sans aucune partie de",
            "max(-eval(child))",
            "quiescence",
        ):
            self.assertIn(token, text)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_shell_parses(self) -> None:
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
