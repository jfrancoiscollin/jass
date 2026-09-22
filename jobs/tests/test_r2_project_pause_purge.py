from __future__ import annotations

import inspect
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

    def test_rehearsal_is_non_destructive(self):
        source = inspect.getsource(p.main)
        self.assertIn('if mode == "production":', source)
        self.assertIn('"dry_run": mode == "rehearsal"', source)

    def test_pre_purge_snapshot_avoids_full_bucket_scan(self):
        source = inspect.getsource(p.main)
        self.assertNotIn('remote_size("r2:jass-data/runs")', source)
        self.assertNotIn('remote_size("r2:jass-data/historical")', source)
        self.assertIn('remote_size("r2:jass-data/inputs")', source)
        self.assertIn('remote_size("r2:jass-data/runtime")', source)


if __name__ == "__main__":
    unittest.main()
