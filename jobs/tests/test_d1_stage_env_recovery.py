from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from jobs.tools import run_experiment_stage as stage


WRAPPER = Path("jobs/templates/l3-d1-wdl-listwise-fit-v3-stage-env-recovery.sh")
BASE = "jobs/templates/l3-d1-wdl-listwise-fit-v2-historical-split.sh"


class D1StageEnvRecoveryTests(unittest.TestCase):
    def test_runner_does_not_propagate_expected_code_sha(self) -> None:
        self.assertNotIn("EXPECTED_CODE_SHA", stage.SAFE_RUNNER_JASS_ENV)
        self.assertEqual(stage.SAFE_RUNNER_JASS_ENV, ("JASS_JOB_ID", "JASS_ATTEMPT_ID"))

    def _repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        (root / "jobs/templates").mkdir(parents=True)
        shutil.copy2(WRAPPER, root / WRAPPER)
        fake = root / BASE
        fake.write_text(
            "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
            "printf '%s\\n' \"$EXPECTED_CODE_SHA\" > \"$JASS_RESULT_DIR/seen-sha.txt\"\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "CI"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        return td, root, head

    def _run(self, root: Path, spec_sha: str) -> subprocess.CompletedProcess[str]:
        result = root / "result"
        artifact = root / "artifact"
        result.mkdir(); artifact.mkdir()
        spec = root / "spec.json"
        spec.write_text(json.dumps({"code_sha": spec_sha}) + "\n", encoding="ascii")
        env = {
            "PATH": os.defpath,
            "JASS_CODE_DIR": str(root),
            "JASS_RESULT_DIR": str(result),
            "JASS_ARTEFACT_DIR": str(artifact),
            "JASS_STAGE_SPEC": str(spec),
            "JASS_JOB_ID": "fixture-d1",
            "JASS_ATTEMPT_ID": "fixture-attempt",
        }
        self.assertNotIn("EXPECTED_CODE_SHA", env)
        return subprocess.run(
            ["/usr/bin/bash", str(root / WRAPPER)], cwd=root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
        )

    def test_wrapper_reconstructs_sha_from_authenticated_spec(self) -> None:
        td, root, head = self._repo()
        self.addCleanup(td.cleanup)
        proc = self._run(root, head)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual((root / "result/seen-sha.txt").read_text().strip(), head)

    def test_wrapper_fails_closed_on_spec_head_mismatch(self) -> None:
        td, root, head = self._repo()
        self.addCleanup(td.cleanup)
        other = "0" * 40 if head != "0" * 40 else "1" * 40
        proc = self._run(root, other)
        self.assertEqual(proc.returncode, 64)
        self.assertIn("stage/spec code mismatch", proc.stderr)
        self.assertFalse((root / "result/seen-sha.txt").exists())


if __name__ == "__main__":
    unittest.main()
