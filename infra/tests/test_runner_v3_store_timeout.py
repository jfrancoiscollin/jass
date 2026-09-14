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
from runner_v3_store import RCLONE_TRANSPORT_ARGS, RcloneResultStore, rclone_rcat_file


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
    @mock.patch("runner_v3_store.rclone_rcat_file")
    @mock.patch("runner_v3_store.run")
    def test_publish_bounds_copy_check_and_streams_marker_last(
        self, mocked_run, mocked_rcat
    ):
        mocked_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        mocked_rcat.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
            uri = RcloneResultStore(cfg(root)).publish(run_dir, "job", "attempt", True)

            self.assertEqual(uri, "r2:jass-data/runs/job/attempt")
            self.assertEqual(mocked_run.call_count, 2)
            commands = [call.args[0] for call in mocked_run.call_args_list]
            self.assertEqual([cmd[1] for cmd in commands], ["copy", "check"])
            for command in commands:
                for index in range(0, len(RCLONE_TRANSPORT_ARGS), 2):
                    flag = RCLONE_TRANSPORT_ARGS[index]
                    value = RCLONE_TRANSPORT_ARGS[index + 1]
                    self.assertIn(flag, command)
                    self.assertEqual(command[command.index(flag) + 1], value)
            self.assertIn("--immutable", commands[0])
            marker = run_dir / "_SUCCESS"
            self.assertTrue(marker.exists())
            mocked_rcat.assert_called_once_with(
                mock.ANY, marker, "r2:jass-data/runs/job/attempt/_SUCCESS"
            )

    @mock.patch("runner_v3_store.subprocess.run")
    def test_rcat_streams_exact_marker_bytes_to_exact_key(self, mocked_subprocess):
        captured = {}

        def invoke(command, **kwargs):
            captured["command"] = command
            captured["bytes"] = kwargs["stdin"].read()
            captured["stdout"] = kwargs["stdout"]
            captured["stderr"] = kwargs["stderr"]
            captured["text"] = kwargs["text"]
            captured["check"] = kwargs["check"]
            return subprocess.CompletedProcess(command, 0, "", "")

        mocked_subprocess.side_effect = invoke
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "_SUCCESS"
            marker.write_bytes(b"2026-09-14T00:00:00+00:00\n")
            result = rclone_rcat_file(
                cfg(root), marker, "r2:jass-data/runs/job/attempt/_SUCCESS"
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured["command"][:3], [
            "rclone", "rcat", "r2:jass-data/runs/job/attempt/_SUCCESS"
        ])
        self.assertEqual(captured["bytes"], b"2026-09-14T00:00:00+00:00\n")
        for index in range(0, len(RCLONE_TRANSPORT_ARGS), 2):
            flag = RCLONE_TRANSPORT_ARGS[index]
            value = RCLONE_TRANSPORT_ARGS[index + 1]
            self.assertIn(flag, captured["command"])
            self.assertEqual(captured["command"][captured["command"].index(flag) + 1], value)
        self.assertIs(captured["stdout"], subprocess.PIPE)
        self.assertIs(captured["stderr"], subprocess.PIPE)
        self.assertTrue(captured["text"])
        self.assertFalse(captured["check"])


if __name__ == "__main__":
    unittest.main()
