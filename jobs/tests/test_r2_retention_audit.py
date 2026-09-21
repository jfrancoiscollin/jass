from __future__ import annotations

import unittest
from jobs.tools import r2_retention_audit as a


class R2RetentionAuditTests(unittest.TestCase):
    def test_terminal_and_schema(self):
        self.assertEqual(a.SCHEMA, "jass.r2_retention_audit.v2")
        self.assertEqual(a.TERMINAL, "R2_RETENTION_PLAN_COMPLETE_V2")

    def test_essential_current_jobs(self):
        self.assertIn("home-1651-l3-scan-ceiling-selection-v1", a.ESSENTIAL_JOBS)
        self.assertIn("cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1", a.ESSENTIAL_JOBS)
        self.assertIn("cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1", a.ESSENTIAL_JOBS)
        self.assertIn("cpx62-2079-l3-chinook-error-mining-v1", a.ESSENTIAL_JOBS)
        self.assertIn("cpx62-2080-l3-chinook-interaction-audit-v1", a.ESSENTIAL_JOBS)
        self.assertIn("cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1", a.ESSENTIAL_JOBS)

    def test_policy(self):
        self.assertEqual(a.keep_reason("historical/x", 10_000_000, ""), "KEEP_NON_RUN_NAMESPACE")
        self.assertEqual(a.keep_reason("runs/old/a/model.pjtw.gz", 10_000_000, "old"), "KEEP_MODEL_ARTIFACT")
        self.assertEqual(a.keep_reason("runs/old/a/log.txt", 1000, "old"), "KEEP_SMALL_METADATA")
        self.assertIsNone(a.keep_reason("runs/old/a/games.gz", 10_000_000, "old"))


if __name__ == "__main__":
    unittest.main()
