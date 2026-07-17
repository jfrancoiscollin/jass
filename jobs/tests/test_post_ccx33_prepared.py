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
FORK_C_T1 = (
    ROOT
    / "jobs/prepared/forkc-teacher-20260717/cpx62-0775-forkc-t1-v1.sh"
)


class PostCcx33PreparedTests(unittest.TestCase):
    def test_all_scripts_are_shell_valid_and_outside_queue(self):
        scripts = sorted(PREPARED.glob("*.sh"))
        self.assertEqual(len(scripts), 5)
        for script in (*TEMPLATES, *scripts, FORK_C_T1):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))

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

    def test_fork_c_t1_requires_c0_and_same_host_mtc(self):
        text = FORK_C_T1.read_text(encoding="utf-8")
        self.assertIn("FORKC_C0_RUN_PREFIX", text)
        self.assertIn("MTC_AUDIT_RUN_PREFIX", text)
        self.assertIn("ALLOW_MTC_SKIP=0", text)
        self.assertIn("--verify-manifest", text)
        self.assertIn("mtc.get('host') != socket.gethostname()", text)


if __name__ == "__main__":
    unittest.main()
