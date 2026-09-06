import importlib.util
import os
from pathlib import Path
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

R2_ENV = [
    "RCLONE_CONFIG_R2_TYPE",
    "RCLONE_CONFIG_R2_PROVIDER",
    "RCLONE_CONFIG_R2_ENDPOINT",
    "RCLONE_CONFIG_R2_ACCESS_KEY_ID",
    "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY",
]


class StageObjectStoreCapabilityTests(unittest.TestCase):
    def test_r2_credentials_are_forwarded_only_when_explicitly_declared(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            result = base / "result"
            artifact = base / "artifact"
            repo.mkdir()
            result.mkdir()
            artifact.mkdir()
            spec_path = base / "spec.json"
            spec_path.write_text("{}\n", encoding="ascii")
            spec = {
                "schema": "jass.stage_spec.v1",
                "campaign": "object-store-contract",
                "stage": "r2-read",
                "code_sha": "a" * 40,
                "command": [sys.executable, "-c", "pass"],
                "working_directory": ".",
                "inputs": [],
                "outputs": [],
                "resources": {"hostname": None, "nproc": None, "clean_worktree": False},
                "timeouts": {"stage_seconds": 10, "terminate_grace_seconds": 1},
                "artifact_directory_contract": "empty_or_runner_launch",
                "environment": {"inherit": list(R2_ENV), "set": {}},
                "scientific_side_effects": {
                    "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
                },
                "success": {"required_exit_code": 0, "next_stage": None},
            }
            runner.validate_spec(spec)
            values = {
                "RCLONE_CONFIG_R2_TYPE": "s3",
                "RCLONE_CONFIG_R2_PROVIDER": "Cloudflare",
                "RCLONE_CONFIG_R2_ENDPOINT": "https://example.invalid",
                "RCLONE_CONFIG_R2_ACCESS_KEY_ID": "access",
                "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "secret",
                "UNRELATED_SECRET": "must-not-leak",
            }
            with mock.patch.dict(os.environ, values, clear=False):
                _cmd, _cwd, env = runner.build_command(
                    spec, repo=repo, result=result, artifact=artifact, spec_path=spec_path,
                )
            for name in R2_ENV:
                self.assertEqual(env[name], values[name])
            self.assertNotIn("UNRELATED_SECRET", env)

    def test_r2_credentials_are_not_implicitly_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            result = base / "result"
            artifact = base / "artifact"
            repo.mkdir()
            result.mkdir()
            artifact.mkdir()
            spec_path = base / "spec.json"
            spec_path.write_text("{}\n", encoding="ascii")
            spec = {
                "schema": "jass.stage_spec.v1",
                "campaign": "object-store-contract",
                "stage": "no-r2",
                "code_sha": "a" * 40,
                "command": [sys.executable, "-c", "pass"],
                "working_directory": ".",
                "inputs": [],
                "outputs": [],
                "resources": {"hostname": None, "nproc": None, "clean_worktree": False},
                "timeouts": {"stage_seconds": 10, "terminate_grace_seconds": 1},
                "artifact_directory_contract": "empty_or_runner_launch",
                "environment": {"inherit": [], "set": {}},
                "scientific_side_effects": {
                    "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
                },
                "success": {"required_exit_code": 0, "next_stage": None},
            }
            values = {name: "secret-value" for name in R2_ENV}
            with mock.patch.dict(os.environ, values, clear=False):
                _cmd, _cwd, env = runner.build_command(
                    spec, repo=repo, result=result, artifact=artifact, spec_path=spec_path,
                )
            for name in R2_ENV:
                self.assertNotIn(name, env)


if __name__ == "__main__":
    unittest.main()
