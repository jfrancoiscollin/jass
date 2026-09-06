from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/run_experiment_stage.py"

spec_module = importlib.util.spec_from_file_location("run_experiment_stage", TOOL)
runner = importlib.util.module_from_spec(spec_module)
assert spec_module.loader is not None
spec_module.loader.exec_module(runner)


class StageRunnerRcloneEnvironmentTests(unittest.TestCase):
    def make_repo(self, base: Path) -> tuple[Path, str]:
        repo = base / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Stage Runner Test"],
            check=True,
        )
        (repo / "tracked.txt").write_text("fixture\n", encoding="ascii")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
        head = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True,
        ).strip()
        return repo, head

    def test_sanitized_stage_keeps_runner_rclone_envelope_only(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            result = base / "result"
            artifact = base / "artifact"
            artifact.mkdir()
            (artifact / "runner-launch.json").write_text("{}\n", encoding="ascii")
            spec_path = base / "spec.json"
            spec = {
                "schema": "jass.stage_spec.v1",
                "campaign": "stage-runner-rclone-env-test",
                "stage": "rclone-env",
                "code_sha": head,
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import os; from pathlib import Path; "
                        "names=['RCLONE_BIN','RCLONE_CONFIG','RCLONE_CONF_B64',"
                        "'RCLONE_CONFIG_R2_TYPE','RCLONE_CONFIG_R2_SECRET_ACCESS_KEY']; "
                        "Path(r'{result_dir}/out.txt').write_text(" 
                        "'\\n'.join([os.environ[name] for name in names] + "
                        "[str('UNRELATED_SECRET' in os.environ)])+'\\n', encoding='ascii')"
                    ),
                ],
                "working_directory": ".",
                "inputs": [],
                "outputs": [{
                    "scope": "result",
                    "path": "out.txt",
                    "kind": "file",
                    "required": True,
                    "nonempty": True,
                }],
                "resources": {
                    "hostname": None,
                    "nproc": None,
                    "clean_worktree": True,
                },
                "timeouts": {
                    "stage_seconds": 10,
                    "terminate_grace_seconds": 1,
                },
                "artifact_directory_contract": "empty_or_runner_launch",
                "environment": {
                    "inherit": [],
                    "set": {},
                },
                "scientific_side_effects": {
                    "fits": 0,
                    "strength_games": 0,
                    "promotions": 0,
                    "bakes": 0,
                },
                "success": {
                    "required_exit_code": 0,
                    "next_stage": "STOP",
                },
            }
            spec_path.write_text(
                __import__("json").dumps(spec, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "RCLONE_BIN": "/usr/bin/rclone",
                    "RCLONE_CONFIG": "/run/jass/rclone.conf",
                    "RCLONE_CONF_B64": "ZmFrZQ==",
                    "RCLONE_CONFIG_R2_TYPE": "s3",
                    "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "fake-secret",
                    "UNRELATED_SECRET": "must-not-leak",
                },
                clear=False,
            ):
                rc, receipt = runner.run_stage(
                    spec_path=spec_path,
                    repo_root=repo,
                    result_dir=result,
                    artifact_dir=artifact,
                )
            self.assertEqual(rc, 0)
            self.assertEqual(receipt["state"], "completed")
            self.assertEqual(
                (result / "out.txt").read_text(encoding="ascii").splitlines(),
                [
                    "/usr/bin/rclone",
                    "/run/jass/rclone.conf",
                    "ZmFrZQ==",
                    "s3",
                    "fake-secret",
                    "False",
                ],
            )


if __name__ == "__main__":
    unittest.main()
