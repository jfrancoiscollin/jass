#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from runner_v3_common import Config
from runner_v3_store import RCLONE_TRANSPORT_ARGS, RcloneResultStore


def cfg(root: Path) -> Config:
    return Config(
        code_repo_dir=root / "code",
        code_remote="origin",
        code_ref="develop",
        control_repo_dir=root / "control",
        control_remote="origin",
        control_ref="main",
        control_layout="v3",
        spool_root=root / "spool",
        result_backend="rclone",
        result_fs_root=root / "published",
        objstore_remote="r2:jass-data",
        objstore_prefix="runs",
        rclone_bin="rclone",
        host_filter="",
        max_log_bytes=1000,
        upload_retries=1,
        git_retries=1,
        allow_legacy_job_paths=False,
        keep_local_results=False,
    )


class RcloneTransportBoundTests(unittest.TestCase):
    @mock.patch("runner_v3_store.run")
    def test_publish_bounds_copy_check_and_marker_transport(self, mocked_run):
        mocked_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
            uri = RcloneResultStore(cfg(root)).publish(run_dir, "job", "attempt", True)

        self.assertEqual(uri, "r2:jass-data/runs/job/attempt")
        self.assertEqual(mocked_run.call_count, 3)
        commands = [call.args[0] for call in mocked_run.call_args_list]
        self.assertEqual([cmd[1] for cmd in commands], ["copy", "check", "copyto"])
        for command in commands:
            for index in range(0, len(RCLONE_TRANSPORT_ARGS), 2):
                flag = RCLONE_TRANSPORT_ARGS[index]
                value = RCLONE_TRANSPORT_ARGS[index + 1]
                self.assertIn(flag, command)
                self.assertEqual(command[command.index(flag) + 1], value)
        self.assertIn("--immutable", commands[0])
        self.assertTrue((run_dir / "_SUCCESS").exists())


if __name__ == "__main__":
    unittest.main()
