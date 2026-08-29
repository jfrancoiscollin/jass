#!/usr/bin/env python3
"""Static guards for the preregistered T3/F6 runtime v3 campaign."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_20260829.md"
R0 = ROOT / "jobs/templates/l3-t3-f6-runtime-r0-v3.sh"
P1 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool1-v3.sh"
P2 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool2-v3.sh"


class RuntimeV3ProtocolTests(unittest.TestCase):
    def test_prereg_preserves_terminals_and_corrects_only_leaf_gate(self) -> None:
        text = PREREG.read_text(encoding="utf-8")
        for token in (
            "R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED",
            "R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED",
            "QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH",
            "R0_V3_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
            "R0_V3_ISOLATED_NEGAMAX_CONTRACT_FAILED",
            "T3_F6_RUNTIME_STRENGTH_SUPPORTED",
            "Aucun Pool3",
        ):
            self.assertIn(token, text)

    def test_all_v3_seeds_are_frozen(self) -> None:
        text = PREREG.read_text(encoding="utf-8")
        for seed in range(2026092101, 2026092107):
            self.assertIn(str(seed), text)
        for seed in range(2026092201, 2026092205):
            self.assertIn(str(seed), text)
        for seed in range(2026092301, 2026092305):
            self.assertIn(str(seed), text)
        self.assertIn("2026092401", text)
        self.assertIn("2026092402", text)

    def test_r0_is_target_blind_and_fail_closed(self) -> None:
        text = R0.read_text(encoding="utf-8")
        for token in (
            "b326bb6610a7eb9b9b997540c1dbb0508f433ca0",
            "CANDIDATES=120000",
            "t3_f6_leaf_contract_v3\" --classify",
            "t3_f6_r0_select_v3.py",
            "--exclude-json-fens",
            "--v3-relative-only",
            "--contract \"$ART/r0-isolated-roots.fen\"",
            "t3_f6_runtime_parity_v2.py",
            "t3_f6_r0_readout_v3.py",
            "t3_f6_negamax_autopsy \\",
            "STRENGTH_GAMES__0",
        ):
            self.assertIn(token, text)

    def test_corrected_probe_and_passive_trace_are_explicit(self) -> None:
        probe = (ROOT / "jobs/tools/t3_f6_leaf_contract_v3.cpp").read_text(
            encoding="utf-8")
        search = (ROOT / "src/search.hpp").read_text(encoding="utf-8")
        for token in (
            "child_reply_capture", "child_opponent_threat",
            "child_selective_sac", "child_forcing_reply",
            "child_promotion_reply", "root_negated_return != -trace->child_return",
            "same_result(out.control.result, out.traced.result)",
            "R0_V3_ISOLATED_NEGAMAX_CONTRACT_FAILED",
            "R0_V3_REAL_SEARCH_SEMANTICS_FAILED",
        ):
            self.assertIn(token, probe)
        self.assertIn("LeafEvalTrace", search)
        self.assertIn("depth_one_trace = nullptr", search)

    def test_pool_wrappers_freeze_native_only_seeds(self) -> None:
        p1 = P1.read_text(encoding="utf-8")
        p2 = P2.read_text(encoding="utf-8")
        for seed in (2026092201, 2026092202, 2026092203):
            self.assertIn(str(seed), p1)
        for seed in (2026092301, 2026092302, 2026092303, 2026092401):
            self.assertIn(str(seed), p2)
        for text in (p1, p2):
            self.assertIn("T3_F6_RUNTIME_CAMPAIGN=v3", text)
            self.assertNotIn("--depth 9", text)

    def test_v3_readouts_freeze_gates_and_decisions(self) -> None:
        r0 = (ROOT / "jobs/tools/t3_f6_r0_readout_v3.py").read_text(encoding="utf-8")
        strength = (ROOT / "jobs/tools/t3_f6_strength_readout_v2.py").read_text(
            encoding="utf-8")
        for token in (
            "R0_V3_PRODUCTION_LEAF_CONTRACT_ESTABLISHED",
            "gate4a_isolated_static_leaf", "gate4b_real_search_semantics",
            "terminal_eval_calls_t0", "R0_V3_PYTHON_NATIVE_PARITY_FAILED",
        ):
            self.assertIn(token, r0)
        for token in (
            "V3_POOL1_BOOTSTRAP_SEED = 2026092203",
            "V3_POOL2_BOOTSTRAP_SEED = 2026092303",
            "V3_CHAINED_BOOTSTRAP_SEED = 2026092401",
            "if p1_rate <= 0.5", "if p2_rate <= 0.5",
            "T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE",
        ):
            self.assertIn(token, strength)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_shell_templates_parse(self) -> None:
        for path in (R0, P1, P2):
            subprocess.run(["bash", "-n", str(path)], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
