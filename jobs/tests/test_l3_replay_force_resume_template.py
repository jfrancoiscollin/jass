#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-exploratory-replay-force-resume-v2.sh"
BASE = ROOT / "jobs/templates/l3-exploratory-replay-four-arm-doe-v1.sh"


class ReplayForceResumeTemplateTest(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)

    def test_pins_failed_source_and_reuses_models(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for token in (
            "ffec746c56930c6236017fe0742017969d27aa5b",
            "cpx62-1449-l3-exploratory-replay-four-arm-doe-v1",
            "20260820T224246Z-7b22be6f",
            "--expected-state failed",
            "MODELS_REUSED_FROM_1449__4",
            "REFITS__0",
            "NEW_SELFPLAY__0",
            "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED",
        ):
            self.assertIn(token, text)

    def test_locks_force_protocol_and_no_fit_invocation(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for token in (
            "NOPEN=1500",
            "POOL_SEED_1=2026082116",
            "POOL_SEED_2=2026082117",
            "BOOTSTRAP=100000",
            "MOVETIME=0.1",
            "FORCE_DEPTH=9",
            '"primary_contrast": "B_vs_A"',
            '"B_vs_C"',
            '"C_vs_D"',
        ):
            self.assertIn(token, text)
        self.assertIn("if 'fit_arm A ' in text", text)
        self.assertIn("resume script still contains a production fit invocation", text)

    def test_proven_pool_name_bug_exists_in_base_and_is_repaired(self) -> None:
        base = BASE.read_text(encoding="utf-8")
        wrapper = TEMPLATE.read_text(encoding="utf-8")
        defective = 'local index="$1" seed="$2" out="replay-doe-pool${index}-openings"'
        self.assertIn(defective, base)
        self.assertIn('local index="$1"\\n  local seed="$2"\\n  local out=', wrapper)
        # Demonstrate the Bash expansion semantics that caused the failure.
        probe = (
            'unset index; f(){ local index="$1" seed="$2" '
            'out="replay-doe-pool${index}-openings"; printf "%s" "$out"; }; f 1 2'
        )
        result = subprocess.run(
            ["bash", "-lc", probe], check=True, text=True, capture_output=True
        )
        self.assertEqual(result.stdout, "replay-doe-pool-openings")


if __name__ == "__main__":
    unittest.main()
