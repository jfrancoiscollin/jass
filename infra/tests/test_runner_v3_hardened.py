#!/usr/bin/env python3
from __future__ import annotations

import shlex
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

    def test_bootstrap_writes_pid_waits_then_execs_wrapper(self):
        pid_path = Path("/tmp/run with space/wrapper.pid")
        ready_path = Path("/tmp/run with space/launcher.ready")
        wrapper = "echo scientific-job-started"
        bootstrap = H.bootstrap_wrapper_command(wrapper, pid_path, ready_path)
        self.assertIn(shlex.quote(str(pid_path)), bootstrap)
        self.assertIn(shlex.quote(str(ready_path)), bootstrap)
        self.assertIn("while [ ! -f", bootstrap)
        self.assertIn("exit 125", bootstrap)
        self.assertIn("exec /usr/bin/bash -c", bootstrap)
        self.assertIn(shlex.quote(wrapper), bootstrap)

    def test_transient_unit_is_independent_unbounded_and_barriered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid_path = root / "runs/job/attempt/wrapper.pid"
            ready_path = pid_path.parent / "launcher.ready"
            unit = H.transient_unit_name(pid_path)
            command = H.systemd_run_command(
                unit, root, "echo ok", pid_path, ready_path
            )
        joined = "\n".join(command)
        self.assertIn("--collect", command)
        self.assertIn("--property=Type=exec", command)
        self.assertIn("--property=KillMode=control-group", command)
        self.assertIn("--property=RuntimeMaxSec=infinity", command)
        self.assertNotIn("--scope", command)
        self.assertIn(unit, joined)
        self.assertIn(str(pid_path), joined)
        self.assertIn(str(ready_path), joined)

    def test_unit_name_is_stable_and_bounded(self):
        path = Path("/var/lib/jass-runner/runs/job/attempt/wrapper.pid")
        first = H.transient_unit_name(path)
        self.assertEqual(first, H.transient_unit_name(path))
        self.assertTrue(first.startswith("jass-job-"))
        self.assertTrue(first.endswith(".service"))
        self.assertLess(len(first), 64)


if __name__ == "__main__":
    unittest.main()
