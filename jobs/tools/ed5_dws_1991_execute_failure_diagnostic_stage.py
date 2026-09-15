#!/usr/bin/env python3
"""Authenticate and republish the bounded Launch V2 failure evidence from ED5 D/W/S barrier 1991.

Pre-target technical diagnostic only. It fetches exactly ``artefacts/attempt-diagnostic.json``
from the failed immutable 1991 attempt. No confirmation target, candidate, control, search,
fit, or alpha-bearing artifact is selected or decoded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
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
PHASES = [
    "authenticate-failed-1991",
    "validate-bounded-execute-failure-evidence",
    "republish-exact-execution-diagnostic",
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
    if not isinstance(value.get("last_phase"), str) or not value["last_phase"]:
        raise RuntimeError("source_diagnostic_last_phase")
    if not isinstance(value.get("error_type"), str) or not value["error_type"]:
        raise RuntimeError("source_diagnostic_error_type")
    frames = value.get("frames")
    if not isinstance(frames, list) or not frames:
        raise RuntimeError("source_diagnostic_frames")
    for frame in frames:
        if not isinstance(frame, dict):
            raise RuntimeError("source_diagnostic_frame_object")
        if not isinstance(frame.get("file"), str) or not frame["file"]:
            raise RuntimeError("source_diagnostic_frame_file")
        if not isinstance(frame.get("line"), int) or frame["line"] <= 0:
            raise RuntimeError("source_diagnostic_frame_line")
        if not isinstance(frame.get("function"), str) or not frame["function"]:
            raise RuntimeError("source_diagnostic_frame_function")


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
        evidence.complete()

        evidence.begin(PHASES[2])
        tmp = artifact / (LOCAL_NAME + ".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, artifact / LOCAL_NAME)
        summary = {
            "schema": "jass.ed5.dws_1991_execute_failure_diagnostic.v1",
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
            "recovered": value,
            **ZERO_FIELDS,
            "scientific_verdict": None,
            "confirmation_authorized": False,
            "next_stage": "PATCH_PROVEN_MECHANICAL_CAUSE_ONLY",
        }
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed5.dws_1991_execute_failure_diagnostic_failure.v1",
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
