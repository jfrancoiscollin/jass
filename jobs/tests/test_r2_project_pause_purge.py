from __future__ import annotations

import unittest
from jobs.tools import r2_project_pause_purge as p


class R2ProjectPausePurgeTests(unittest.TestCase):
    def test_hard_final_limit(self):
        self.assertEqual(p.MAX_FINAL_BYTES, 10 * 1024**3)
        self.assertLess(p.MAX_CAPSULE_BYTES, p.MAX_FINAL_BYTES)

    def test_capsule_outside_purged_prefix(self):
        self.assertIn("/pause/", p.CAPSULE)
        self.assertNotIn("/runs/", p.CAPSULE)

    def test_required_restart_assets(self):
        self.assertEqual(set(p.REQUIRED), {"champion","context30","turnover","hier","scan_reference"})


if __name__ == "__main__":
    unittest.main()
