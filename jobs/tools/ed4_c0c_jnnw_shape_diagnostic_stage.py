#!/usr/bin/env python3
"""Localize the authenticated JNNW envelope failure seen in C0C 1907.

C0C 1907's immutable traceback ends at ``parse_jnnw`` line 74, the
``jnnw_trailing_bytes`` guard.  Runner stdout/stderr are both authenticated
empty.  This diagnostic replays the already-frozen C0A/C0B candidate order and
checks only JNNW container envelopes until the first malformed object is found.
It does not decode any record fields or canonical position identity and never
reads ED4 confirmation targets, scores, WDL, q-values, models, teacher/search
results, fits or games.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
from typing import Any, BinaryIO

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
SOURCE_JOB = "cpx62-1907-l3-ed4-c0c-structural-exclusion-union-v4"
SOURCE_ATTEMPT = "20260910T145830Z-96b4d879"
SOURCE_CODE = "96b4d87920485d3836132c54c2e26c16241fdde7"
EXPECTED_FAILURE_TOKEN = "jnnw_trailing_bytes"
REC = 38
PHASES = [
    "authenticate-c0b-parent-metadata",
    "scan-authenticated-jnnw-envelopes",
    "publish-jnnw-shape-diagnostic",
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


def _open_jnnw(path: Path, compressed: bool) -> BinaryIO:
    return gzip.open(path, "rb") if compressed else path.open("rb")


def inspect_jnnw_envelope(path: Path, compressed: bool) -> dict[str, Any]:
    """Check only magic/count/body-length; never decode any record bytes."""
    with _open_jnnw(path, compressed) as stream:
        header = stream.read(8)
        if len(header) != 8 or header[:4] != b"JNNW":
            return {"state": "invalid", "reason": "jnnw_header", "declared_count": None}
        count = struct.unpack("<I", header[4:])[0]
        remaining = count * REC
        consumed = 0
        while remaining:
            chunk = stream.read(min(1 << 20, remaining))
            if not chunk:
                return {
                    "state": "invalid",
                    "reason": "jnnw_truncated",
                    "declared_count": count,
                    "declared_body_bytes": count * REC,
                    "consumed_body_bytes": consumed,
                }
            consumed += len(chunk)
            remaining -= len(chunk)
        trailing = stream.read(1)
        if trailing:
            return {
                "state": "invalid",
                "reason": "jnnw_trailing_bytes",
                "declared_count": count,
                "declared_body_bytes": count * REC,
                "consumed_body_bytes": consumed,
            }
    return {
        "state": "valid",
        "reason": None,
        "declared_count": count,
        "declared_body_bytes": count * REC,
        "consumed_body_bytes": consumed,
    }


def find_first_jnnw_failure(
    c0a: dict[str, Any], c0b: dict[str, Any], work: Path
) -> dict[str, Any]:
    sources = {row["job_id"]: row for row in c0a.get("sources", [])}
    checked = 0
    downloaded_bytes = 0
    inventories_authenticated = 0
    zero_size_skipped = 0

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
        prefix = f"r2:jass-data/runs/{job_id}/{attempt}"
        inventory_report = fetch_result_files.inspect_result_inventory(
            rclone="rclone", prefix=prefix, expected_state=state,
        )
        identity = (
            inventory_report.get("job_id"), inventory_report.get("attempt_id"),
            inventory_report.get("code_sha"), inventory_report.get("result_state"),
        )
        if identity != (job_id, attempt, source.get("code_sha"), state):
            raise RuntimeError("candidate_inventory_identity")
        inventories_authenticated += 1
        inventory = {item["path"]: item for item in inventory_report.get("files", [])}

        for index, desc in enumerate(candidates):
            if desc.get("kind") not in {"jnnw", "jnnw_gzip"}:
                continue
            item = inventory.get(desc["path"])
            if item is None or item.get("size_bytes") != desc.get("size_bytes") or item.get("sha256") != desc.get("sha256"):
                raise RuntimeError("descriptor_drift")
            if item["size_bytes"] == 0:
                zero_size_skipped += 1
                continue
            local_dir = work / ("job-" + hashlib.sha256(job_id.encode()).hexdigest()[:12])
            local_name = f"{index:04d}-{Path(desc['path']).name}"
            fetched = fetch_result_files.fetch_files(
                rclone="rclone",
                prefix=prefix,
                expected_state=state,
                selections=[(desc["path"], local_name)],
                out_dir=local_dir,
            )
            got = fetched["files"][0]
            if got.get("sha256") != desc.get("sha256") or got.get("size_bytes") != desc.get("size_bytes"):
                raise RuntimeError("descriptor_drift_after_download")
            checked += 1
            downloaded_bytes += int(got["size_bytes"])
            local_path = local_dir / local_name
            shape = inspect_jnnw_envelope(local_path, desc["kind"] == "jnnw_gzip")
            local_path.unlink(missing_ok=True)
            shutil.rmtree(local_dir, ignore_errors=True)
            if shape["state"] == "invalid":
                return {
                    "first_failure": {
                        "job_id": job_id,
                        "attempt_id": attempt,
                        "path": desc["path"],
                        "kind": desc["kind"],
                        "sha256": desc["sha256"],
                        "size_bytes": desc["size_bytes"],
                        **shape,
                    },
                    "jnnw_files_checked": checked,
                    "candidate_payload_reads": checked,
                    "candidate_payload_bytes_read": downloaded_bytes,
                    "candidate_inventories_authenticated": inventories_authenticated,
                    "zero_size_jnnw_skipped": zero_size_skipped,
                }

    return {
        "first_failure": None,
        "jnnw_files_checked": checked,
        "candidate_payload_reads": checked,
        "candidate_payload_bytes_read": downloaded_bytes,
        "candidate_inventories_authenticated": inventories_authenticated,
        "zero_size_jnnw_skipped": zero_size_skipped,
    }


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    evidence = StageEvidence(artifact, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        c0a, c0b = fetch_parent_metadata(result / "c0c-jnnw-shape-parent")
        evidence.complete()

        evidence.begin(PHASES[1])
        diagnostic = find_first_jnnw_failure(c0a, c0b, result / "c0c-jnnw-shape-work")
        first = diagnostic.get("first_failure")
        if not first:
            raise RuntimeError("no_jnnw_shape_failure_reproduced")
        if first.get("reason") != EXPECTED_FAILURE_TOKEN:
            raise RuntimeError("unexpected_jnnw_failure_token")
        evidence.complete()

        evidence.begin(PHASES[2])
        output = {
            "schema": "jass.ed4.c0c_jnnw_shape_diagnostic.v1",
            "state": "completed",
            "classification": "TECHNICAL_STRUCTURAL_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE,
            "parent_job_id": PARENT_JOB,
            "parent_attempt_id": PARENT_ATTEMPT,
            "parent_c0a_sha256": C0A_SHA,
            "parent_c0b_sha256": C0B_SHA,
            "expected_failure_token": EXPECTED_FAILURE_TOKEN,
            **diagnostic,
            "record_fields_decoded": 0,
            "position_identity_reads": 0,
            "target_fields_decoded": 0,
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
            "next_stage": "ED4_C0C_CLASSIFY_AUTHENTICATED_MALFORMED_JNNW",
        }
        atomic_json(artifact / "ed4-c0c-jnnw-shape-diagnostic.json", output)
        atomic_json(artifact / "scientific-summary.json", output)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.c0c_jnnw_shape_diagnostic_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "scientific_verdict": None,
            "confirmation_authorized": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
