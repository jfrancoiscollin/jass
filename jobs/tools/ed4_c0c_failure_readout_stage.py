#!/usr/bin/env python3
"""Authenticate the failed ED4 C0C 1898 attempt and publish only technical diagnostics.

This stage reads runner-owned stage receipt/stdout/stderr from the already-failed
attempt. It never opens any scientific payload, position corpus, target, model,
score, WDL, q-value, teacher output or search result.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from jobs.tools import fetch_result_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SOURCE_JOB = "cpx62-1898-l3-ed4-c0c-structural-exclusion-union-v1"
SOURCE_ATTEMPT = "20260909T212744Z-2bf3785b"
SOURCE_CODE = "2bf3785bcf3bafcb048c64cd2de1f85cbdc7cd45"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
PHASES = ["authenticate-failed-attempt", "read-runner-diagnostics", "publish-technical-readout"]
MAX_TAIL_BYTES = 8192


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_text_tail(path: Path, limit: int = MAX_TAIL_BYTES) -> str:
    raw = path.read_bytes()
    return raw[-limit:].decode("utf-8", errors="replace")


def summarize_receipt(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != "jass.stage_receipt.v1":
        raise RuntimeError("stage_receipt_schema")
    if value.get("state") != "failed":
        raise RuntimeError("stage_receipt_not_failed")
    if value.get("code_sha") != SOURCE_CODE:
        raise RuntimeError("stage_receipt_code_identity")
    return {
        "state": value.get("state"),
        "failure_class": value.get("failure_class"),
        "failure_stage": value.get("failure_stage"),
        "error": value.get("error"),
        "exit_code": value.get("exit_code"),
        "timed_out": value.get("timed_out"),
        "duration_seconds": value.get("duration_seconds"),
        "inputs_authenticated": value.get("inputs_authenticated"),
        "outputs_authenticated": value.get("outputs_authenticated"),
        "stage": value.get("stage"),
        "code_sha": value.get("code_sha"),
    }


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    evidence = StageEvidence(artifact, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        out = result / "c0c-1898-failure-readout"
        report = fetch_result_files.fetch_files(
            rclone="rclone",
            prefix=SOURCE_PREFIX,
            expected_state="failed",
            selections=[
                ("stage-receipt.json", "stage-receipt.json"),
                ("stage.stdout.log", "stage.stdout.log"),
                ("stage.stderr.log", "stage.stderr.log"),
            ],
            out_dir=out,
        )
        identity = (
            report.get("job_id"), report.get("attempt_id"), report.get("code_sha"),
            report.get("result_state"), report.get("exit_code"),
        )
        if identity != (SOURCE_JOB, SOURCE_ATTEMPT, SOURCE_CODE, "failed", 2):
            raise RuntimeError("failed_attempt_identity")
        evidence.complete()

        evidence.begin(PHASES[1])
        receipt_path = out / "stage-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise RuntimeError("stage_receipt_object")
        stage = summarize_receipt(receipt)
        stdout_path = out / "stage.stdout.log"
        stderr_path = out / "stage.stderr.log"
        technical = {
            "schema": "jass.ed4.c0c_failure_readout.v1",
            "state": "completed",
            "classification": "TECHNICAL_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE,
            "stage_receipt": stage,
            "stage_receipt_sha256": sha256_file(receipt_path),
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "stdout_size_bytes": stdout_path.stat().st_size,
            "stderr_size_bytes": stderr_path.stat().st_size,
            "stdout_tail": bounded_text_tail(stdout_path),
            "stderr_tail": bounded_text_tail(stderr_path),
            "scientific_payload_reads": 0,
            "target_reads": 0,
            "score_reads": 0,
            "wdl_reads": 0,
            "qvalue_reads": 0,
            "model_reads": 0,
            "teacher_calls": 0,
            "search_calls": 0,
            "fits": 0,
            "games": 0,
            "alpha_spent": 0,
            "scientific_verdict": None,
            "confirmation_authorized": False,
            "automatic_continuation": False,
        }
        evidence.complete()

        evidence.begin(PHASES[2])
        atomic_json(artifact / "ed4-c0c-failure-readout.json", technical)
        summary = dict(technical)
        summary["next_stage"] = "ED4_C0C_TECHNICAL_REPAIR_FROM_AUTHENTICATED_1898_DIAGNOSTIC"
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.c0c_failure_readout_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "scientific_verdict": None,
            "confirmation_authorized": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
