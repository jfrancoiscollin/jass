#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

warnings.simplefilter("ignore", ResourceWarning)
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import runner_v3 as R
from runner_v3_common import Config, control_paths, read_json, status_path, write_json
from runner_v3_git import git_sync_code, git_sync_control
from runner_v3_store import (
    FilesystemResultStore,
    inventory_files,
    remote_join,
    sha256_file,
    truncate_and_gzip,
    write_checksums,
)


def cfg(root: Path, *, layout: str = "v3", backend: str = "filesystem") -> Config:
    return Config(
        code_repo_dir=root / "code",
        code_remote="origin",
        code_ref="develop",
        control_repo_dir=root / "control",
        control_remote="origin",
        control_ref="control",
        control_layout=layout,
        spool_root=root / "spool",
        result_backend=backend,
        result_fs_root=root / "published",
        objstore_remote="r2:jass" if backend == "rclone" else "",
        objstore_prefix="runs",
        rclone_bin="rclone",
        host_filter="",
        max_log_bytes=32,
        upload_retries=1,
        git_retries=1,
        allow_legacy_job_paths=False,
        keep_local_results=False,
    )


class ConfigTests(unittest.TestCase):
    def test_develop_is_mandatory(self):
        with tempfile.TemporaryDirectory() as td:
            c = cfg(Path(td))
            object.__setattr__(c, "code_ref", "main")
            with self.assertRaises(ValueError):
                c.validate()

    def test_code_and_control_must_be_separate(self):
        with tempfile.TemporaryDirectory() as td:
            c = cfg(Path(td))
            object.__setattr__(c, "control_repo_dir", c.code_repo_dir)
            with self.assertRaises(ValueError):
                c.validate()


class LayoutTests(unittest.TestCase):
    def test_v3_layout(self):
        with tempfile.TemporaryDirectory() as td:
            c = cfg(Path(td), layout="v3")
            paths = control_paths(c)
            self.assertEqual(paths.queue_pending, c.control_repo_dir / "queue/pending")
            self.assertEqual(status_path(c, "job"), c.control_repo_dir / "status/job.json")

    def test_legacy_layout(self):
        with tempfile.TemporaryDirectory() as td:
            c = cfg(Path(td), layout="legacy")
            paths = control_paths(c)
            self.assertEqual(paths.queue_pending, c.control_repo_dir / "jobs/queue")
            self.assertEqual(
                status_path(c, "job"),
                c.control_repo_dir / "jobs/results/job/status.json",
            )

    def test_candidates_respect_terminal_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            c = cfg(root, layout="legacy")
            paths = control_paths(c)
            paths.queue_pending.mkdir(parents=True)
            (paths.queue_pending / "a.sh").write_text("echo a")
            (paths.queue_pending / "b.sh").write_text("echo b")
            write_json(status_path(c, "a"), {"state": "completed"})
            self.assertEqual([x.name for x in R.candidate_jobs(c)], ["b.sh"])

    def test_job_rejects_main_and_root_jass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            c = cfg(root)
            script = root / "job.sh"
            script.write_text("cd /root/jass\ngit fetch origin main\n")
            with self.assertRaises(RuntimeError):
                R.validate_job_script(c, script)

    def test_job_accepts_neighbour_root_jass_installs(self):
        # /root/jass-scan (binaire Scan) et /root/jass-runner ne sont PAS le
        # clone de code legacy /root/jass : ils ne doivent pas être rejetés.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            c = cfg(root)
            script = root / "job.sh"
            script.write_text(
                'cd "$JASS_CODE_DIR"\n'
                'SCAN_BIN=/root/jass-scan/scan_linux\n'
                '"$SCAN_BIN" --version\n'
            )
            R.validate_job_script(c, script)

    def test_job_accepts_v3_environment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            c = cfg(root)
            script = root / "job.sh"
            script.write_text('cd "$JASS_CODE_DIR"\necho ok > "$JASS_ARTEFACT_DIR/x"\n')
            R.validate_job_script(c, script)

    def test_job_env_forwards_only_rclone_configuration_and_is_private(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(
            os.environ,
            {
                "RCLONE_BIN": "/usr/bin/rclone",
                "RCLONE_CONFIG_R2_TYPE": "s3",
                "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "secret with space",
                "UNRELATED_SECRET": "must-not-leak",
            },
            clear=True,
        ):
            path = Path(td) / "job.env"
            R.write_job_env(path, {"JASS_CODE_DIR": "/tmp/work with space"})
            text = path.read_text(encoding="utf-8")
            self.assertIn("export RCLONE_CONFIG_R2_TYPE=s3\n", text)
            self.assertIn(
                "export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY='secret with space'\n",
                text,
            )
            self.assertIn("export JASS_CODE_DIR='/tmp/work with space'\n", text)
            self.assertNotIn("UNRELATED_SECRET", text)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class ResultTests(unittest.TestCase):
    def test_inventory_and_checksums(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("abc")
            files = inventory_files(root)
            self.assertEqual(files[0]["path"], "a.txt")
            self.assertEqual(files[0]["sha256"], sha256_file(root / "a.txt"))
            write_checksums(root, files)
            self.assertIn("a.txt", (root / "checksums.sha256").read_text())

    def test_filesystem_store_writes_marker_last(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "manifest.json").write_text("{}")
            store = FilesystemResultStore(root / "published")
            uri = store.publish(run_dir, "job", "attempt", True)
            destination = Path(uri.removeprefix("file://"))
            self.assertTrue((destination / "_SUCCESS").exists())
            self.assertFalse((destination / "_FAILED").exists())

    def test_remote_join(self):
        self.assertEqual(
            remote_join("r2:bucket/", "/runs/", "job", "a"),
            "r2:bucket/runs/job/a",
        )

    def test_log_is_truncated_and_gzipped(self):
        import gzip

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            output = root / "out.gz"
            raw.write_bytes(b"x" * 100)
            truncate_and_gzip(raw, output, 10)
            with gzip.open(output, "rb") as handle:
                data = handle.read()
            self.assertTrue(data.startswith(b"...[truncated]..."))
            self.assertTrue(data.endswith(b"x" * 10))

    def test_status_inlines_only_allowlisted_small_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "nested").mkdir()
            (root / "nested/teacher-smoke-decision.json").write_text(
                json.dumps({"scientific_status": "confirm_b1", "winner": "B1"})
            )
            (root / "secret.json").write_text(json.dumps({"token": "do-not-copy"}))
            (root / "promotion.json").write_text("not-json")
            payload = R.artefact_status_payload(root)
            self.assertEqual(len(payload["artefacts"]), 3)
            self.assertEqual(
                payload["scientific_summaries"][
                    "nested/teacher-smoke-decision.json"
                ]["winner"],
                "B1",
            )
            self.assertNotIn("secret.json", payload["scientific_summaries"])
            self.assertNotIn("promotion.json", payload["scientific_summaries"])

    def test_missing_exit_code_creates_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "artefacts").mkdir()
            info = {
                "run_dir": str(run_dir),
                "job_id": "job",
                "attempt_id": "attempt",
                "host": "host",
                "code_sha": "a" * 40,
            }
            self.assertEqual(R.read_exit_code(info), (-1, "missing_exit_code"))
            R.write_attempt_diagnostic(info, "missing_exit_code")
            diagnostic = read_json(run_dir / "artefacts/attempt-diagnostic.json")
            self.assertEqual(diagnostic["reason"], "missing_exit_code")
            self.assertEqual(
                diagnostic["classification"],
                "wrapper_terminated_without_exit_status",
            )


class JsonTests(unittest.TestCase):
    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x/a.json"
            write_json(path, {"b": 1})
            self.assertEqual(json.loads(path.read_text()), {"b": 1})
            self.assertFalse(path.with_suffix(".json.tmp").exists())


class EndToEndFilesystemTests(unittest.TestCase):
    def git(self, cwd: Path, *args: str):
        import subprocess

        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        )

    def seed_repo(
        self, root: Path, name: str, branch: str, files: dict[str, str]
    ) -> Path:
        source = root / f"{name}-src"
        remote = root / f"{name}.git"
        clone = root / name
        source.mkdir()
        self.git(source, "init", "-b", branch)
        self.git(source, "config", "user.name", "Test")
        self.git(source, "config", "user.email", "test@example.com")
        for relative, content in files.items():
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git(source, "add", ".")
        self.git(source, "commit", "-m", "seed")
        self.git(root, "clone", "--bare", str(source), str(remote))
        self.git(root, "clone", str(remote), str(clone))
        self.git(clone, "config", "user.name", "Runner")
        self.git(clone, "config", "user.email", "runner@example.com")
        return clone

    def test_v3_claim_run_publish_and_done(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            code = self.seed_repo(root, "code", "develop", {"README.md": "code\n"})
            job = (
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                'cd "$JASS_CODE_DIR"\n'
                'echo ok > "$JASS_ARTEFACT_DIR/result.txt"\n'
                'echo \'{"scientific_status":"complete_probe"}\' '
                '> "$JASS_ARTEFACT_DIR/scientific-summary.json"\n'
            )
            control = self.seed_repo(
                root,
                "control",
                "main",
                {
                    "queue/pending/smoke.sh": job,
                    "queue/running/.gitkeep": "",
                    "queue/done/.gitkeep": "",
                    "status/.gitkeep": "",
                    "state/.gitkeep": "",
                },
            )
            c = Config(
                code_repo_dir=code,
                code_remote="origin",
                code_ref="develop",
                control_repo_dir=control,
                control_remote="origin",
                control_ref="main",
                control_layout="v3",
                spool_root=root / "spool",
                result_backend="filesystem",
                result_fs_root=root / "published",
                objstore_remote="",
                objstore_prefix="runs",
                rclone_bin="rclone",
                host_filter="",
                max_log_bytes=1000,
                upload_retries=1,
                git_retries=2,
                allow_legacy_job_paths=False,
                keep_local_results=False,
            )
            git_sync_code(code, "origin", "develop")
            git_sync_control(control, "origin", "main")
            R.bootstrap_dirs(c)
            claimed = R.claim_job(c, R.candidate_jobs(c)[0])
            info = R.start_job(c, claimed)
            deadline = time.time() + 10
            while R.alive(R.wrapper_pid(info)) and time.time() < deadline:
                time.sleep(0.05)
            self.assertFalse(R.alive(R.wrapper_pid(info)))
            self.assertTrue(R.reap_finished_job(c))
            status = read_json(status_path(c, "smoke"))
            self.assertEqual(status["state"], "completed")
            self.assertEqual(
                status["scientific_summaries"]["scientific-summary.json"]
                ["scientific_status"],
                "complete_probe",
            )
            published = root / "published/smoke" / info["attempt_id"]
            self.assertTrue((published / "_SUCCESS").exists())
            self.assertEqual(
                (published / "artefacts/result.txt").read_text().strip(), "ok"
            )
            self.assertTrue((control / "queue/done/smoke.sh").exists())


if __name__ == "__main__":
    unittest.main()
