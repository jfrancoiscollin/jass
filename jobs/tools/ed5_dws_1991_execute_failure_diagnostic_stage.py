#!/usr/bin/env python3
"""Authenticate ED5 barrier 1991 failure evidence and reproduce its direct entrypoint failure.

Pre-target technical diagnostic only. It fetches exactly ``artefacts/attempt-diagnostic.json``
from failed immutable attempt 1991, republishes those exact bytes, and if the Launch V2
failure has no StageEvidence traceback, executes only the byte-identical barrier wrapper
with all ED5 source identity variables removed. That probe cannot progress to source fetches,
confirmation targets, candidate/control evaluation, search, fitting, or alpha accounting.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SOURCE_JOB = "cpx62-1991-l3-ed5-fresh-dws-historical-disjointness-rehearsal-v2"
SOURCE_ATTEMPT = "20260915T173419Z-ae1fdd65"
SOURCE_CODE_SHA = "ae1fdd65bfdedf024562536fca1da842272ea14c"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
SOURCE_REMOTE_PATH = "artefacts/attempt-diagnostic.json"
LOCAL_NAME = "recovered-attempt-diagnostic-1991.json"
PROBE_NAME = "direct-script-probe-1991.json"
WRAPPER_REL = "jobs/tools/ed5_fresh_dws_disjointness_current_stage.py"
WRAPPER_GIT_BLOB_SHA = "548dde8f84458f41c0e18d7bef2c374b7fc55f99"
PHASES = [
    "authenticate-failed-1991",
    "republish-exact-launch-failure",
    "reproduce-direct-script-entrypoint",
    "classify-proven-mechanical-cause",
]
ZERO_FIELDS = {
    "target_reads": 0,
    "candidate_reads": 0,
    "control_evaluations": 0,
    "scan_searches": 0,
    "jass_searches": 0,
    "fits": 0,
    "alpha_spent": 0,
    "confirmation_target_consumed": False,
}


def validate_source_diagnostic(value: dict) -> None:
    required = {
        "schema": "jass.launch_failure.v2",
        "classification": "TECHNICAL",
        "state": "failed",
        "failure_code": "STAGE_FAILED:EXECUTE",
        "scientific_verdict": None,
        "job_id": SOURCE_JOB,
        "attempt_id": SOURCE_ATTEMPT,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise RuntimeError(f"source_diagnostic_{key}")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def direct_entrypoint_probe(result: Path) -> dict:
    wrapper = ROOT / WRAPPER_REL
    wrapper_raw = wrapper.read_bytes()
    observed_blob = git_blob_sha(wrapper_raw)
    if observed_blob != WRAPPER_GIT_BLOB_SHA:
        raise RuntimeError("wrapper_not_byte_identical_to_1991")

    probe_art = result / "probe-art"
    probe_result = result / "probe-result"
    probe_art.mkdir(parents=True, exist_ok=True)
    probe_result.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    for key in list(env):
        if key.startswith("ED5_FRESH_"):
            env.pop(key, None)
    env["LAUNCH_MODE"] = "rehearsal"
    env["JASS_ARTEFACT_DIR"] = str(probe_art)
    env["JASS_RESULT_DIR"] = str(probe_result)
    completed = subprocess.run(
        ["/usr/bin/python3", WRAPPER_REL],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return {
        "schema": "jass.ed5.dws_1991_direct_script_probe.v1",
        "wrapper_rel": WRAPPER_REL,
        "wrapper_git_blob_sha": observed_blob,
        "python": "/usr/bin/python3",
        "cwd": str(ROOT),
        "ed5_identity_environment_removed": True,
        "pythonpath_removed": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        **ZERO_FIELDS,
        "scientific_verdict": None,
        "confirmation_authorized": False,
    }


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    evidence = StageEvidence(artifact, mode)
    try:
        if mode != "rehearsal":
            raise RuntimeError("diagnostic_requires_rehearsal")
        artifact.mkdir(parents=True, exist_ok=True)
        recovered_dir = result / "recovered-1991"

        evidence.begin(PHASES[0])
        receipt = fetch_files(
            rclone="rclone",
            prefix=SOURCE_PREFIX,
            selections=[(SOURCE_REMOTE_PATH, LOCAL_NAME)],
            out_dir=recovered_dir,
            expected_state="failed",
        )
        observed = (
            receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"),
            receipt.get("result_state"), receipt.get("exit_code"),
        )
        if observed != (SOURCE_JOB, SOURCE_ATTEMPT, SOURCE_CODE_SHA, "failed", 2):
            raise RuntimeError("failed_1991_identity")
        files = receipt.get("files", [])
        if len(files) != 1 or files[0].get("path") != SOURCE_REMOTE_PATH:
            raise RuntimeError("failed_1991_selection")
        evidence.complete()

        evidence.begin(PHASES[1])
        source_path = recovered_dir / LOCAL_NAME
        raw = source_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("source_diagnostic_object")
        validate_source_diagnostic(value)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        if files[0].get("sha256") != source_sha256 or files[0].get("size_bytes") != len(raw):
            raise RuntimeError("failed_1991_artifact_identity")
        tmp = artifact / (LOCAL_NAME + ".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, artifact / LOCAL_NAME)
        evidence.complete()

        evidence.begin(PHASES[2])
        probe = direct_entrypoint_probe(result)
        atomic_json(artifact / PROBE_NAME, probe)
        evidence.complete()

        evidence.begin(PHASES[3])
        stderr = probe["stderr"]
        import_failure = (
            probe["returncode"] != 0
            and "ModuleNotFoundError" in stderr
            and "No module named 'jobs'" in stderr
            and WRAPPER_REL in stderr
        )
        if not import_failure:
            raise RuntimeError("direct_entrypoint_failure_not_reproduced")
        bounded_frames_available = all(value.get(key) for key in ("last_phase", "error_type", "frames"))
        summary = {
            "schema": "jass.ed5.dws_1991_execute_failure_diagnostic.v2",
            "state": "completed",
            "classification": "TECHNICAL_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE_SHA,
            "source_expected_state": "failed",
            "source_exit_code": 2,
            "source_artifact_path": SOURCE_REMOTE_PATH,
            "source_artifact_sha256": source_sha256,
            "source_artifact_size_bytes": len(raw),
            "source_stage_evidence_available": bounded_frames_available,
            "recovered": value,
            "probe": probe,
            "proven_root_cause": "DIRECT_SCRIPT_IMPORT_PATH",
            "proven_exception": "ModuleNotFoundError: No module named 'jobs'",
            "repair_scope": "bootstrap repository root in ed5_fresh_dws_disjointness_current_stage.py before importing jobs.tools",
            **ZERO_FIELDS,
            "scientific_verdict": None,
            "confirmation_authorized": False,
            "next_stage": "PATCH_DIRECT_SCRIPT_IMPORT_PLUMBING_ONLY",
        }
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed5.dws_1991_execute_failure_diagnostic_failure.v2",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            **ZERO_FIELDS,
            "scientific_verdict": None,
            "confirmation_authorized": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
