from __future__ import annotations

import unittest

from jobs.tools import ed4_c0c_failure_readout_stage as stage


class C0C1903DiagnosticIdentityTests(unittest.TestCase):
    def test_immutable_source_identity(self):
        self.assertEqual(stage.SOURCE_JOB, "cpx62-1903-l3-ed4-c0c-structural-exclusion-union-v3")
        self.assertEqual(stage.SOURCE_ATTEMPT, "20260910T111237Z-731ae702")
        self.assertEqual(stage.SOURCE_CODE, "731ae702ce60d2dc830a97171e6721dc892575c1")
        self.assertEqual(
            stage.SOURCE_PREFIX,
            "r2:jass-data/runs/cpx62-1903-l3-ed4-c0c-structural-exclusion-union-v3/20260910T111237Z-731ae702",
        )
        self.assertEqual(stage.DIAGNOSTIC_PATHS, ("stage-receipt.json", "stage.stdout.log", "stage.stderr.log"))


if __name__ == "__main__":
    unittest.main()
