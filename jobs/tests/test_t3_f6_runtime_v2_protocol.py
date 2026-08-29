#!/usr/bin/env python3
"""Static protocol guards for the preregistered T3/F6 runtime v2 campaign."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V2_20260829.md"
R0 = ROOT / "jobs/templates/l3-t3-f6-runtime-r0-v2.sh"
P1 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool1-v2.sh"
P2 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool2-v2.sh"


class RuntimeV2ProtocolTests(unittest.TestCase):
    def test_prereg_freezes_relative_question_and_v1_terminal(self) -> None:
        text = PREREG.read_text(encoding="utf-8")
        for token in (
            "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "FROZEN_CURRICULUM_FAILS_PREREGISTERED_COLOUR_IMAGE_EXACTNESS",
            "extra_engine",
            "max(abs(extra_float)) <= 1e-10",
            "1e-10",
            "R0_RELATIVE_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
            "T3_F6_RUNTIME_STRENGTH_SUPPORTED",
            "ni Pool3",
        ):
            self.assertIn(token, text)

    def test_all_seeds_are_frozen_before_new_scores(self) -> None:
        text = PREREG.read_text(encoding="utf-8")
        for seed in range(2026091701, 2026091705):
            self.assertIn(str(seed), text)
        for seed in range(2026091801, 2026091805):
            self.assertIn(str(seed), text)
        for seed in range(2026091901, 2026091905):
            self.assertIn(str(seed), text)
        self.assertIn("2026092001", text)
        self.assertIn("2026092002", text)

    def test_r0_references_prereg_and_excludes_terminal_v1_corpus(self) -> None:
        text = R0.read_text(encoding="utf-8")
        for token in (
            "b6c747091aea265cd3f7ddeb4175fe05912ad255",
            "2026091701", "2026091702", "2026091703", "2026091704",
            "--expected-state \"$T3_F6_R0_V1_EXPECTED_STATE\"",
            "t3_f6_relative_probe",
            "t3_f6_runtime_parity_v2.py",
            "t3_f6_r0_readout_v2.py",
        ):
            self.assertIn(token, text)

    def test_cpx_strength_is_native_only_and_q00_nonblocking(self) -> None:
        p1 = P1.read_text(encoding="utf-8")
        p2 = P2.read_text(encoding="utf-8")
        for text in (p1, p2):
            self.assertIn("--movetime 0.1", text)
            self.assertNotIn("--depth 9", text)
            self.assertNotIn("pool1-q00", text)
            self.assertNotIn("pool2-q00", text)
            self.assertIn("Q00_GAMES__0", text)
        for seed in (2026091801, 2026091802, 2026091803):
            self.assertIn(str(seed), p1)
        for seed in (2026091901, 2026091902, 2026091903, 2026092001):
            self.assertIn(str(seed), p2)

    def test_relative_probe_has_exact_relative_and_negamax_gates(self) -> None:
        text = (ROOT / "jobs/tools/t3_f6_relative_probe.cpp").read_text(encoding="utf-8")
        for token in (
            "engine_extra_mismatches == 0",
            "max_abs_extra_float <= 1e-10",
            "f6_colour_mismatch_rows",
            "residual_colour_mismatch_rows",
            "negamax_single_inversion",
            "terminal_precedence",
            "tablebase_precedence",
        ):
            self.assertIn(token, text)

    def test_strength_readout_freezes_native_decisions(self) -> None:
        text = (ROOT / "jobs/tools/t3_f6_strength_readout_v2.py").read_text(encoding="utf-8")
        for token in (
            "POOL1_BOOTSTRAP_SEED = 2026091803",
            "POOL2_BOOTSTRAP_SEED = 2026091903",
            "CHAINED_BOOTSTRAP_SEED = 2026092001",
            "if p1_rate <= 0.5",
            "if p2_rate <= 0.5",
            "chained_native[\"ci_low\"]",
            "T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE",
        ):
            self.assertIn(token, text)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_shell_templates_parse(self) -> None:
        for path in (R0, P1, P2):
            subprocess.run(["bash", "-n", str(path)], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
