#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARED = ROOT / "jobs/prepared/post-ccx33-20260717"
TEMPLATES = (
    ROOT / "jobs/templates/attempt-diagnostic-runner-v3.sh",
    ROOT / "jobs/templates/conversion-teacher-confirm-runner-v3.sh",
    ROOT / "jobs/templates/mtc-audit-runner-v3.sh",
    ROOT / "jobs/templates/p3-blind-holdout-runner-v3.sh",
)
# Fork C T1 (cpx62-0775) ANNULÉ le 2026-07-17 : le C0 a rendu stop_regression
# (cf docs/archives/forkc_c0_verdict_20260717.md). Le script est retiré du jeu préparé.


class PostCcx33PreparedTests(unittest.TestCase):
    def test_all_scripts_are_shell_valid_and_outside_queue(self):
        scripts = sorted(PREPARED.glob("*.sh"))
        self.assertEqual(len(scripts), 5)
        for script in (*TEMPLATES, *scripts):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))

    def test_fork_c_t1_is_cancelled(self):
        removed = (
            ROOT
            / "jobs/prepared/forkc-teacher-20260717/cpx62-0775-forkc-t1-v1.sh"
        )
        self.assertFalse(removed.exists(), "fork C T1 doit rester annulé (C0 stop_regression)")

    def test_mtc_audit_is_concurrent_and_fail_closed(self):
        text = TEMPLATES[2].read_text(encoding="utf-8")
        self.assertIn("--require-smoke", text)
        self.assertIn("MTC_AUDIT_MAX_PROCS", text)
        self.assertIn("pids+=(\"$!\")", text)
        self.assertIn("--egdb-mtc-probe", text)

    def test_holdout_is_candidate_blind_and_powered(self):
        text = TEMPLATES[3].read_text(encoding="utf-8")
        self.assertIn("--player-pattern \"$W/T0.pjtw\"", text)
        self.assertIn("conversion_confirmation_gate.py plan", text)
        self.assertIn("cache_guard.py", text)
        self.assertIn("--verify-manifest", text)
        self.assertIn("'blind_to_teacher_candidate':True", text)
        self.assertIn("mtc.get('host') != socket.gethostname()", text)
        self.assertNotIn("B1.pjtw", text)

    def test_confirmation_uses_one_preengaged_winner(self):
        text = TEMPLATES[1].read_text(encoding="utf-8")
        self.assertIn("smoke does not authorize one winner", text)
        self.assertIn("mtc.get('host') != socket.gethostname()", text)
        self.assertIn("conversion_confirmation_gate.py confirm", text)
        self.assertIn("--verify-manifest", text)
        self.assertIn("CACHE_PROCS=$((PAR_CONV * 3))", text)

if __name__ == "__main__":
    unittest.main()
