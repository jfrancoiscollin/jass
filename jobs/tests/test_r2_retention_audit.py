from __future__ import annotations

import unittest
from jobs.tools import r2_retention_audit as a


class R2RetentionAuditTests(unittest.TestCase):
    def test_job_regex(self):
        sample = "cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1 home-1651-l3-scan-ceiling-selection-v1"
        got = set(a.JOB_RE.findall(sample))
        self.assertIn("cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1", got)
        self.assertIn("home-1651-l3-scan-ceiling-selection-v1", got)

    def test_read_only_terminal(self):
        self.assertEqual(a.TERMINAL, "R2_RETENTION_AUDIT_COMPLETE_V1")


if __name__ == "__main__":
    unittest.main()
