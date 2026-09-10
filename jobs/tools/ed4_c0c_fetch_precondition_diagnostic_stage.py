#!/usr/bin/env python3
"""Authenticate the metadata needed to explain C0C 1903's fetch guard failure.

The failed 1903 traceback reached ``fetch_result_files.fetch_files`` at the
missing/empty selected-file guard.  Runner stdout/stderr were both authenticated
empty by 1904, so the exact offending candidate cannot be recovered from logs.
This diagnostic therefore replays only the already-frozen C0A/C0B metadata and
runner inventories.  It never downloads a candidate payload and never decodes a
position, target, score, WDL, q-value, model, teacher or search result.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import fetch_result_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PARENT_JOB = "cpx62-1897-l3-ed4-c0b-structural-payload-freeze-v2"
PARENT_ATTEMPT = "20260909T210053Z-a3efc988"
PARENT_CODE = "a3efc988d8ff0b5642ab65fa0bf133897ee2f54c"
PARENT_PREFIX = f"r2:jass-data/runs/{PARENT_JOB}/{PARENT_ATTEMPT}"
C0A_PATH = "artefacts/ed4-c0a-source-descriptor-inventory.json"
C0B_PATH = "artefacts/ed4-c0b-structural-candidate-manifest.json"
C0A_SHA = "0af828dbc84b7103ad2aa54196c2ca18f81b3afab01b4daa6e256ffd87ecb219"
C0B_SHA = "c04c5ad0a3c6b98d6d3c86575f1ba5607cdad17e92ae5b1ed4108aeb81274bda"
SOURCE_JOB = "cpx62-1903-l3-ed4-c0c-structural-exclusion-union-v3"
SOURCE_ATTEMPT = "20260910T111237Z-731ae702"
SOURCE_CODE = "731ae702ce60d2dc830a97171e6721dc892575c1"
PHASES = [
    "authenticate-c0b-parent-metadata",
    "authenticate-candidate-inventories",
    "publish-fetch-precondition-diagnostic",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("metadata_json_object_required")
    return value


def fetch_parent_metadata(out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    report = fetch_result_files.fetch_files(
        rclone="rclone",
        prefix=PARENT_PREFIX,
        expected_state="completed",
        selections=[(C0A_PATH, "c0a.json"), (C0B_PATH, "c0b.json")],
        out_dir=out_dir,
    )
    identity = (
        report.get("job_id"), report.get("attempt_id"), report.get("code_sha"),
        report.get("result_state"), report.get("exit_code"),
    )
    if identity != (PARENT_JOB, PARENT_ATTEMPT, PARENT_CODE, "completed", 0):
        raise RuntimeError("parent_identity")
    if sha256_file(out_dir / "c0a.json") != C0A_SHA:
        raise RuntimeError("c0a_hash")
    if sha256_file(out_dir / "c0b.json") != C0B_SHA:
        raise RuntimeError("c0b_hash")
    return read_json(out_dir / "c0a.json"), read_json(out_dir / "c0b.json")


def classify_fetch_preconditions(
    c0a: dict[str, Any],
    c0b: dict[str, Any],
    inventories: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Mirror only the pre-download guard used by C0C's ``fetch_files`` call."""
    sources = {row["job_id"]: row for row in c0a.get("sources", [])}
    blockers: list[dict[str, Any]] = []
    drifts: list[dict[str, Any]] = []
    examined = 0
    jobs_examined = 0

    for job in c0b.get("candidate_jobs", []):
        job_id = job["job_id"]
        attempt = job.get("attempt_id")
        candidates = job.get("candidate_files", [])
        if not candidates:
            continue
        source = sources.get(job_id)
        if not source or source.get("attempt_id") != attempt:
            raise RuntimeError("c0a_c0b_identity_mismatch")
        state = source.get("result_state")
        if state not in {"completed", "failed"}:
            raise RuntimeError("candidate_result_state")
        report = inventories.get((job_id, attempt))
        if report is None:
            raise RuntimeError("candidate_inventory_missing")
        identity = (
            report.get("job_id"), report.get("attempt_id"), report.get("code_sha"),
            report.get("result_state"),
        )
        if identity != (job_id, attempt, source.get("code_sha"), state):
            raise RuntimeError("candidate_inventory_identity")
        files = {item["path"]: item for item in report.get("files", [])}
        jobs_examined += 1
        for desc in candidates:
            examined += 1
            path = desc["path"]
            item = files.get(path)
            if item is None:
                blockers.append({
                    "job_id": job_id, "attempt_id": attempt, "path": path,
                    "reason": "MISSING_FROM_AUTHENTICATED_INVENTORY",
                    "declared_size_bytes": desc.get("size_bytes"),
                    "declared_sha256": desc.get("sha256"),
                })
                continue
            if item.get("size_bytes") <= 0:
                blockers.append({
                    "job_id": job_id, "attempt_id": attempt, "path": path,
                    "reason": "ZERO_SIZE_AUTHENTICATED_CANDIDATE",
                    "declared_size_bytes": desc.get("size_bytes"),
                    "inventory_size_bytes": item.get("size_bytes"),
                    "declared_sha256": desc.get("sha256"),
                    "inventory_sha256": item.get("sha256"),
                })
            if (
                item.get("size_bytes") != desc.get("size_bytes")
                or item.get("sha256") != desc.get("sha256")
            ):
                drifts.append({
                    "job_id": job_id, "attempt_id": attempt, "path": path,
                    "declared_size_bytes": desc.get("size_bytes"),
                    "inventory_size_bytes": item.get("size_bytes"),
                    "declared_sha256": desc.get("sha256"),
                    "inventory_sha256": item.get("sha256"),
                })

    return {
        "candidate_jobs_examined": jobs_examined,
        "candidate_files_examined": examined,
        "fetch_guard_blockers": blockers,
        "fetch_guard_blocker_count": len(blockers),
        "first_fetch_guard_blocker": blockers[0] if blockers else None,
        "descriptor_drifts": drifts,
        "descriptor_drift_count": len(drifts),
    }


def authenticate_candidate_inventories(
    c0a: dict[str, Any], c0b: dict[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    sources = {row["job_id"]: row for row in c0a.get("sources", [])}
    reports: dict[tuple[str, str], dict[str, Any]] = {}
    for job in c0b.get("candidate_jobs", []):
        candidates = job.get("candidate_files", [])
        if not candidates:
            continue
        job_id = job["job_id"]
        attempt = job.get("attempt_id")
        source = sources.get(job_id)
        if not source or source.get("attempt_id") != attempt:
            raise RuntimeError("c0a_c0b_identity_mismatch")
        state = source.get("result_state")
        if state not in {"completed", "failed"}:
            raise RuntimeError("candidate_result_state")
        prefix = f"r2:jass-data/runs/{job_id}/{attempt}"
        report = fetch_result_files.inspect_result_inventory(
            rclone="rclone", prefix=prefix, expected_state=state,
        )
        reports[(job_id, attempt)] = report
    return reports


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    evidence = StageEvidence(artifact, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        metadata_dir = result / "c0c-fetch-precondition-metadata"
        c0a, c0b = fetch_parent_metadata(metadata_dir)
        evidence.complete()

        evidence.begin(PHASES[1])
        inventories = authenticate_candidate_inventories(c0a, c0b)
        diagnostic = classify_fetch_preconditions(c0a, c0b, inventories)
        if diagnostic["fetch_guard_blocker_count"] == 0:
            raise RuntimeError("no_fetch_guard_blocker_reproduced")
        evidence.complete()

        evidence.begin(PHASES[2])
        output = {
            "schema": "jass.ed4.c0c_fetch_precondition_diagnostic.v1",
            "state": "completed",
            "classification": "TECHNICAL_METADATA_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE,
            "parent_job_id": PARENT_JOB,
            "parent_attempt_id": PARENT_ATTEMPT,
            "parent_c0a_sha256": C0A_SHA,
            "parent_c0b_sha256": C0B_SHA,
            **diagnostic,
            "metadata_payload_reads": 2,
            "candidate_payload_reads": 0,
            "position_identity_reads": 0,
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
            "next_stage": "ED4_C0C_CLASSIFY_PROVEN_FETCH_GUARD_BLOCKER",
        }
        atomic_json(artifact / "ed4-c0c-fetch-precondition-diagnostic.json", output)
        atomic_json(artifact / "scientific-summary.json", output)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.c0c_fetch_precondition_diagnostic_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "scientific_verdict": None,
            "confirmation_authorized": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
