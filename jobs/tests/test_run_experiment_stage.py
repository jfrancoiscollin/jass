import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/run_experiment_stage.py"

spec_module = importlib.util.spec_from_file_location("run_experiment_stage", TOOL)
runner = importlib.util.module_from_spec(spec_module)
assert spec_module.loader is not None
spec_module.loader.exec_module(runner)


class ExperimentStageRunnerTests(unittest.TestCase):
    def make_repo(self, base: Path) -> tuple[Path, str]:
        repo = base / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Stage Runner Test"], check=True)
        (repo / "input.txt").write_text("fixture\n", encoding="ascii")
        subprocess.run(["git", "-C", str(repo), "add", "input.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        return repo, head

    def base_spec(self, repo: Path, head: str) -> dict:
        raw = (repo / "input.txt").read_bytes()
        return {
            "schema": "jass.stage_spec.v1",
            "campaign": "stage-runner-test",
            "stage": "echo",
            "code_sha": head,
            "command": [
                sys.executable,
                "-c",
                "from pathlib import Path; Path(r'{result_dir}/out.txt').write_text('ok\\n', encoding='ascii')",
            ],
            "working_directory": ".",
            "inputs": [{
                "scope": "repo",
                "path": "input.txt",
                "required": True,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            }],
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
                "inherit": ["PATH"],
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
                "next_stage": "next-stage",
            },
        }

    def write_spec(self, path: Path, spec: dict) -> None:
        path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="ascii")

    def invoke(self, base: Path, spec: dict, *, artifact_extra: str | None = None):
        repo = base / "repo"
        spec_path = base / "spec.json"
        result = base / "result"
        artifact = base / "artifact"
        artifact.mkdir()
        (artifact / "runner-launch.json").write_text("{}\n", encoding="ascii")
        if artifact_extra is not None:
            (artifact / artifact_extra).write_text("x\n", encoding="ascii")
        self.write_spec(spec_path, spec)
        rc, receipt = runner.run_stage(
            spec_path=spec_path,
            repo_root=repo,
            result_dir=result,
            artifact_dir=artifact,
        )
        return rc, receipt, result, artifact

    def test_success_writes_receipt_outside_artifact_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            rc, receipt, result, artifact = self.invoke(base, spec)
            self.assertEqual(rc, 0)
            self.assertEqual(receipt["state"], "completed")
            self.assertIsNone(receipt["failure_class"])
            self.assertTrue(receipt["inputs_authenticated"])
            self.assertTrue(receipt["outputs_authenticated"])
            self.assertEqual(receipt["next_stage"], "next-stage")
            self.assertEqual(sorted(p.name for p in artifact.iterdir()), ["runner-launch.json"])
            self.assertEqual((result / "out.txt").read_text(encoding="ascii"), "ok\n")
            raw = (result / "stage-receipt.json").read_bytes()
            parsed = json.loads(raw)
            self.assertEqual(raw, runner.canonical_json_bytes(parsed))

    def test_unexpected_artifact_file_fails_before_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            rc, receipt, result, _artifact = self.invoke(base, spec, artifact_extra="contamination.txt")
            self.assertEqual(rc, 2)
            self.assertEqual(receipt["failure_class"], "PRECONDITION")
            self.assertEqual(receipt["failure_stage"], "ARTIFACT_PRECONDITION")
            self.assertFalse((result / "out.txt").exists())

    def test_input_hash_mismatch_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            spec["inputs"][0]["sha256"] = "0" * 64
            rc, receipt, _result, _artifact = self.invoke(base, spec)
            self.assertEqual(rc, 2)
            self.assertEqual(receipt["failure_class"], "PRECONDITION")
            self.assertEqual(receipt["failure_stage"], "INPUTS")
            self.assertIn("input SHA mismatch", receipt["error"])

    def test_nonzero_stage_exit_is_classified(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            spec["command"] = [sys.executable, "-c", "raise SystemExit(7)"]
            rc, receipt, _result, _artifact = self.invoke(base, spec)
            self.assertEqual(rc, 2)
            self.assertEqual(receipt["failure_class"], "STAGE_EXIT_CODE")
            self.assertEqual(receipt["failure_stage"], "EXECUTE")
            self.assertEqual(receipt["exit_code"], 7)

    def test_missing_required_output_is_classified(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            spec["command"] = [sys.executable, "-c", "pass"]
            rc, receipt, _result, _artifact = self.invoke(base, spec)
            self.assertEqual(rc, 2)
            self.assertEqual(receipt["failure_class"], "EXECUTION")
            self.assertEqual(receipt["failure_stage"], "OUTPUTS")
            self.assertIn("required output missing", receipt["error"])

    def test_jass_environment_inheritance_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, head = self.make_repo(base)
            spec = self.base_spec(repo, head)
            spec["environment"]["inherit"] = ["PATH", "JASS_SECRET"]
            spec_path = base / "spec.json"
            self.write_spec(spec_path, spec)
            with self.assertRaises(runner.StageSpecError):
                runner.read_spec(spec_path)


if __name__ == "__main__":
    unittest.main()
