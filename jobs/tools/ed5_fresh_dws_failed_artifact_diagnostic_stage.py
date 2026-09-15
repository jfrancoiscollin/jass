#!/usr/bin/env python3
"""Authenticate failed ED5 disjointness rehearsal 1985 and republish its exact report.

This is a pre-target technical diagnostic only. It fetches exactly the already-written
``artefacts/dws-historical-disjointness.json`` from the failed runner-v3 result and
never reads any confirmation target, candidate, control score, teacher/search output,
or fit artifact.
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

SOURCE_JOB = "cpx62-1985-l3-ed5-fresh-dws-historical-disjointness-rehearsal-v1"
SOURCE_ATTEMPT = "20260915T103638Z-9e8eb2a3"
SOURCE_CODE_SHA = "9e8eb2a32d80f15491ef1ff6bb5aa3b95edcdc49"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
SOURCE_REMOTE_PATH = "artefacts/dws-historical-disjointness.json"
LOCAL_NAME = "dws-historical-disjointness.json"
PHASES = [
    "authenticate-failed-1985",
    "validate-pre-target-artifact",
    "republish-exact-overlap-report",
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


def validate_source_report(value: dict) -> None:
    required = {
        "schema": "jass.ed5.fresh_dws_historical_disjointness.v1",
        "state": "failed",
        "terminal": "ED5_FRESH_DWS_HISTORICAL_COLLISION_TECHNICAL_FAILURE_V1",
        "pairwise_and_historical_disjoint": False,
        **ZERO_FIELDS,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise RuntimeError(f"source_report_{key}")
    for key in ("sources", "counts", "pairwise_overlaps", "historical_overlaps", "historical_sources"):
        if not isinstance(value.get(key), dict):
            raise RuntimeError(f"source_report_{key}")


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    evidence = StageEvidence(artifact, mode)
    try:
        if mode != "rehearsal":
            raise RuntimeError("diagnostic_requires_rehearsal")
        artifact.mkdir(parents=True, exist_ok=True)
        recovered_dir = result / "recovered-1985"

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
            raise RuntimeError("failed_1985_identity")
        files = receipt.get("files", [])
        if len(files) != 1 or files[0].get("path") != SOURCE_REMOTE_PATH:
            raise RuntimeError("failed_1985_selection")
        evidence.complete()

        evidence.begin(PHASES[1])
        source_path = recovered_dir / LOCAL_NAME
        raw = source_path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("source_report_object")
        validate_source_report(value)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        if files[0].get("sha256") != source_sha256 or files[0].get("size_bytes") != len(raw):
            raise RuntimeError("failed_1985_artifact_identity")
        evidence.complete()

        evidence.begin(PHASES[2])
        tmp = artifact / (LOCAL_NAME + ".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, artifact / LOCAL_NAME)
        summary = {
            "schema": "jass.ed5.fresh_dws_failed_artifact_diagnostic.v1",
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
            "next_stage": "REPAIR_ONLY_PROVEN_PRE_TARGET_CANONICAL_COLLISIONS",
        }
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed5.fresh_dws_failed_artifact_diagnostic_failure.v1",
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
