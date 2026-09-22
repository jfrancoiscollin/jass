from __future__ import annotations

import unittest
from jobs.tools import r2_pause_capsule as c


class PauseCapsuleTests(unittest.TestCase):
    def test_budget_below_user_limit(self):
        self.assertLess(c.MAX_CAPSULE_BYTES, 10 * 1024**3)

    def test_core_lineage_retained(self):
        required = {
            "home-0977-l3-pure-turnover1to1-train-v1",
            "cpx62-1340-jass-megacorpus-comparative-fit-v1",
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1",
            "cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1",
            "cpx62-2079-l3-chinook-error-mining-v1",
            "cpx62-2080-l3-chinook-interaction-audit-v1",
            "cpx62-2081-l3-chinook-hybrid-strength-rehearsal-v1",
        }
        self.assertTrue(required <= set(c.KEEP_JOBS))

    def test_capsule_target_outside_runs(self):
        self.assertIn("/pause/", c.TARGET)
        self.assertNotIn("/runs/", c.TARGET)

    def test_index_publisher_uses_resilient_copy(self):
        import inspect
        source = inspect.getsource(c.publish_index)
        self.assertIn("\"copy\"", source)
        self.assertIn("\"--immutable\"", source)
        self.assertIn("\"--retries\"", source)
        self.assertNotIn("\"copyto\"", source)


if __name__ == "__main__":
    unittest.main()
