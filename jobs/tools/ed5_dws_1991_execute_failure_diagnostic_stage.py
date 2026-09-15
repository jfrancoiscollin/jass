#!/usr/bin/env python3
"""Authenticate the minimal runner evidence needed to diagnose ED5 barrier 1991.

Pre-target technical diagnostic only. The failed Launch V2 wrapper diagnostic did not
contain stage frames because the stage failed before execution evidence was created.
This readout therefore fetches only the runner-owned ``stage-receipt.json`` and
``stage.stderr.log`` from the exact failed immutable attempt. It never selects or
decodes confirmation targets, candidates, controls, search outputs, fits, or alpha.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
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
SOURCE_RECEIPT_REMOTE = "stage-receipt.json"
SOURCE_STDERR_REMOTE = "stage.stderr.log"
RECEIPT_LOCAL = "recovered-stage-receipt-1991.json"
STDERR_LOCAL = "recovered-stage-stderr-1991.log"
PHASES = [
    "authenticate-failed-1991-runner-evidence",
    "validate-execute-stderr",
    "republish-bounded-exception",
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
FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>[1-9][0-9]*), in (?P<function>.+?)\s*$')
EXCEPTION_RE = re.compile(r'^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?:: (?P<message>.*))?$')


def validate_stage_receipt(value: dict, stderr_raw: bytes) -> None:
    required = {
        "schema": "jass.stage_receipt.v1",
        "state": "failed",
        "failure_stage": "EXECUTE",
        "code_sha": SOURCE_CODE_SHA,
        "outputs_authenticated": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise RuntimeError(f"source_receipt_{key}")
    exit_code = value.get("exit_code")
    if not isinstance(exit_code, int) or exit_code == 0:
        raise RuntimeError("source_receipt_exit_code")
    descriptor = value.get("stderr")
    if not isinstance(descriptor, dict):
        raise RuntimeError("source_receipt_stderr_descriptor")
    if descriptor.get("sha256") != hashlib.sha256(stderr_raw).hexdigest():
        raise RuntimeError("source_receipt_stderr_sha256")
    if descriptor.get("size_bytes") != len(stderr_raw):
        raise RuntimeError("source_receipt_stderr_size")


def parse_exception(stderr_raw: bytes) -> dict:
    if not stderr_raw or len(stderr_raw) > 1_000_000:
        raise RuntimeError("source_stderr_size")
    try:
        text = stderr_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("source_stderr_utf8") from exc
    lines = [line.rstrip("\r") for line in text.splitlines()]
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        raise RuntimeError("source_stderr_empty")
    match = EXCEPTION_RE.fullmatch(nonempty[-1].strip())
    if match is None:
        raise RuntimeError("source_stderr_exception_line")
    message = match.group("message") or ""
    if len(message) > 500 or any(ord(ch) < 32 and ch not in "\t" for ch in message):
        raise RuntimeError("source_stderr_exception_message")
    frames = []
    for line in lines:
        frame = FRAME_RE.fullmatch(line)
        if frame is not None:
            frames.append({
                "file": Path(frame.group("file")).name,
                "line": int(frame.group("line")),
                "function": frame.group("function")[:120],
            })
    if not frames:
        raise RuntimeError("source_stderr_frames")
    return {
        "error_type": match.group("type"),
        "error_message": message,
        "frames": frames[-6:],
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
        selections = [
            (SOURCE_RECEIPT_REMOTE, RECEIPT_LOCAL),
            (SOURCE_STDERR_REMOTE, STDERR_LOCAL),
        ]
        fetched = fetch_files(
            rclone="rclone",
            prefix=SOURCE_PREFIX,
            selections=selections,
            out_dir=recovered_dir,
            expected_state="failed",
        )
        observed = (
            fetched.get("job_id"), fetched.get("attempt_id"), fetched.get("code_sha"),
            fetched.get("result_state"), fetched.get("exit_code"),
        )
        if observed != (SOURCE_JOB, SOURCE_ATTEMPT, SOURCE_CODE_SHA, "failed", 2):
            raise RuntimeError("failed_1991_identity")
        files = fetched.get("files", [])
        if [entry.get("path") for entry in files] != [SOURCE_RECEIPT_REMOTE, SOURCE_STDERR_REMOTE]:
            raise RuntimeError("failed_1991_selection")
        evidence.complete()

        evidence.begin(PHASES[1])
        receipt_raw = (recovered_dir / RECEIPT_LOCAL).read_bytes()
        stderr_raw = (recovered_dir / STDERR_LOCAL).read_bytes()
        receipt = json.loads(receipt_raw.decode("utf-8"))
        if not isinstance(receipt, dict):
            raise RuntimeError("source_receipt_object")
        validate_stage_receipt(receipt, stderr_raw)
        exception = parse_exception(stderr_raw)
        expected_files = {
            SOURCE_RECEIPT_REMOTE: receipt_raw,
            SOURCE_STDERR_REMOTE: stderr_raw,
        }
        for entry in files:
            raw = expected_files[entry["path"]]
            if entry.get("sha256") != hashlib.sha256(raw).hexdigest() or entry.get("size_bytes") != len(raw):
                raise RuntimeError("failed_1991_artifact_identity")
        evidence.complete()

        evidence.begin(PHASES[2])
        for local_name, raw in ((RECEIPT_LOCAL, receipt_raw), (STDERR_LOCAL, stderr_raw)):
            tmp = artifact / (local_name + ".tmp")
            tmp.write_bytes(raw)
            os.replace(tmp, artifact / local_name)
        summary = {
            "schema": "jass.ed5.dws_1991_execute_failure_diagnostic.v2",
            "state": "completed",
            "classification": "TECHNICAL_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE_SHA,
            "source_expected_state": "failed",
            "source_exit_code": 2,
            "stage_exit_code": receipt["exit_code"],
            "stage_failure_class": receipt.get("failure_class"),
            "stage_failure_stage": receipt["failure_stage"],
            "stage_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "stage_stderr_sha256": hashlib.sha256(stderr_raw).hexdigest(),
            "stage_stderr_size_bytes": len(stderr_raw),
            "exception": exception,
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
