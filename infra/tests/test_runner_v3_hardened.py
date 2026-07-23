#!/usr/bin/env python3
from __future__ import annotations

import json
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

    def test_launch_contract_exists_before_systemd_starts_job(self):
        class Client:
            returncode = 0

            def communicate(self):
                return "", ""

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "runs/job/attempt"
            run_dir.mkdir(parents=True)
            metadata_path = run_dir / "metadata.json"
            metadata_path.write_text(json.dumps({"job_id": "job"}))
            pid_path = run_dir / "wrapper.pid"
            raw_log = run_dir / "output.log.raw"
            wrapper = (
                f"exec >{raw_log} 2>&1; echo $$ > {pid_path}; "
                f"source {run_dir / 'job.env'}; bash {run_dir / 'job.sh'}"
            )

            def fake_popen(command, **kwargs):
                metadata = json.loads(metadata_path.read_text())
                self.assertEqual(metadata["launcher"], "systemd-transient-service")
                self.assertEqual(metadata["launcher_state"], "launching")
                self.assertTrue(metadata["parent_runner_cgroup_isolated"])
                self.assertTrue(metadata["systemd_unit"].startswith("jass-job-"))
                report = json.loads((run_dir / "artefacts/runner-launch.json").read_text())
                self.assertEqual(report["state"], "launching")
                pid_path.write_text("4321\n")
                return Client()

            proc = H.launch_transient(
                ["bash", "-c", wrapper],
                {"cwd": str(Path(td)), "start_new_session": True},
                fake_popen,
            )
            self.assertEqual(proc.pid, 4321)
            metadata = json.loads(metadata_path.read_text())
            self.assertEqual(metadata["launcher_state"], "running")
            self.assertEqual(metadata["wrapper_pid"], 4321)
            report = json.loads((run_dir / "artefacts/runner-launch.json").read_text())
            self.assertEqual(report["state"], "running")
            self.assertEqual(report["wrapper_pid"], 4321)


if __name__ == "__main__":
    unittest.main()
