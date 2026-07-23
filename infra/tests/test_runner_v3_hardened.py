#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import runner_v3_hardened as H


class HardenedLauncherTests(unittest.TestCase):
    def test_extract_wrapper_pid_path(self):
        wrapper = (
            "set +e; exit_file=/tmp/exit; "
            "exec >/tmp/output.log.raw 2>&1; "
            "echo $$ > '/tmp/run with space/wrapper.pid'; "
            "source /tmp/job.env; cd /tmp/work; bash /tmp/job.sh"
        )
        self.assertEqual(
            H.extract_wrapper_pid_path(wrapper),
            Path("/tmp/run with space/wrapper.pid"),
        )

    def test_recognises_only_runner_job_launch(self):
        wrapper = (
            "exec >/tmp/output.log.raw 2>&1; echo $$ > /tmp/wrapper.pid; "
            "source /tmp/job.env; bash /tmp/job.sh"
        )
        self.assertTrue(H.is_runner_job_launch(
            ["bash", "-c", wrapper],
            {"start_new_session": True},
        ))
        self.assertFalse(H.is_runner_job_launch(
            ["git", "status"],
            {"start_new_session": True},
        ))
        self.assertFalse(H.is_runner_job_launch(
            ["bash", "-c", wrapper],
            {"start_new_session": False},
        ))

    def test_transient_unit_is_independent_and_unbounded(self):
        with tempfile.TemporaryDirectory() as td:
            pid_path = Path(td) / "runs/job/attempt/wrapper.pid"
            unit = H.transient_unit_name(pid_path)
            command = H.systemd_run_command(unit, Path(td), "echo ok")
        joined = "\n".join(command)
        self.assertIn("--collect", command)
        self.assertIn("--property=Type=exec", command)
        self.assertIn("--property=KillMode=control-group", command)
        self.assertIn("--property=RuntimeMaxSec=infinity", command)
        self.assertNotIn("--scope", command)
        self.assertIn(unit, joined)

    def test_unit_name_is_stable_and_bounded(self):
        path = Path("/var/lib/jass-runner/runs/job/attempt/wrapper.pid")
        first = H.transient_unit_name(path)
        self.assertEqual(first, H.transient_unit_name(path))
        self.assertTrue(first.startswith("jass-job-"))
        self.assertTrue(first.endswith(".service"))
        self.assertLess(len(first), 64)


if __name__ == "__main__":
    unittest.main()
