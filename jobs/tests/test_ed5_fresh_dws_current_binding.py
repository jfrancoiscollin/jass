from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from jobs.tools import ed5_fresh_dws_disjointness_current_stage as stage


class Ed5FreshDwsCurrentBindingTests(unittest.TestCase):
    def test_wrapper_requires_and_binds_explicit_d_identity(self):
        identity = (
            "cpx62-1990-l3-ed5-fresh-d-source-production-v2",
            "20260915T000000Z-deadbeef",
            "a" * 40,
        )
        env = {
            "ED5_FRESH_D_JOB": identity[0],
            "ED5_FRESH_D_ATTEMPT": identity[1],
            "ED5_FRESH_D_CODE_SHA": identity[2],
        }
        original = stage.barrier.D
        try:
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage.barrier, "main", return_value=0) as run:
                self.assertEqual(stage.main(), 0)
                self.assertEqual(stage.barrier.D, identity)
                run.assert_called_once_with()
        finally:
            stage.barrier.D = original

    def test_direct_script_import_bootstraps_repo_root_before_jobs_import(self):
        repo = Path(__file__).resolve().parents[2]
        script = repo / "jobs/tools/ed5_fresh_dws_disjointness_current_stage.py"
        probe = (
            "import importlib.util, pathlib, sys\n"
            f"repo = pathlib.Path({str(repo)!r})\n"
            f"script = pathlib.Path({str(script)!r})\n"
            "sys.path[:] = [str(script.parent)] + [p for p in sys.path if p not in ('', str(repo))]\n"
            "spec = importlib.util.spec_from_file_location('ed5_direct_probe', script)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "print('DIRECT_IMPORT_OK')\n"
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd="/",
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "DIRECT_IMPORT_OK")

    def test_profile_is_read_only_and_uses_current_d_wrapper(self):
        profile = Path(__file__).resolve().parents[1] / "launch_profiles/ed5-fresh-dws-historical-disjointness-v2.json"
        obj = json.loads(profile.read_text())
        self.assertEqual(obj["command"], ["/usr/bin/python3", "jobs/tools/ed5_fresh_dws_disjointness_current_stage.py"])
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            effects = obj[mode]
            self.assertEqual(effects["test_target_reads"], 0)
            self.assertEqual(effects["new_scan_searches"], 0)
            self.assertEqual(effects["new_jass_searches"], 0)
            self.assertEqual(effects["fits"], 0)
            self.assertEqual(effects["strength_games"], 0)
            self.assertEqual(effects["promotions"], 0)
            self.assertEqual(effects["bakes"], 0)


if __name__ == "__main__":
    unittest.main()
