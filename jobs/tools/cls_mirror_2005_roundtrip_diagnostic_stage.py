#!/usr/bin/env python3
"""Bounded technical readout for failed CLS mirror production 2005.

The immutable production failed inside Launch-V2 authentication with
PUBLISHED_OUTPUT_ROUNDTRIP before the scientific stage ran.  This diagnostic
re-fetches only the exact authenticated rehearsal evidence that the gate itself
compared, reproduces the gate's published-output hashing, and reports the exact
mismatching artifact names/hashes.  It performs no target reads, fits, strength
games, alpha spending, promotion, bake, or new engine search.
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
from jobs.tools.launch_gate_v2 import published_output_sha, sha
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SOURCE_JOB = "cpx62-2004-l3-cls-mirror-scale-rehearsal-v3"
SOURCE_ATTEMPT = "20260916T124649Z-f769bc39"
SOURCE_CODE_SHA = "f769bc396ab8a9cd9e473908ca62b96fc54f1076"
SOURCE_RECEIPT_SHA256 = "1e86eaa354265a09078fe12cd8b1b5c35630e31141fbe7b305008dbd9bc448f4"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"

PROFILE_EVIDENCE = [
    "deep_reference.tsv",
    "aggregates.json",
    "bootstrap.json",
    "mirror-evidence.json",
    "source-authentication.json",
    "root-selection.json",
    "full-root-ids.txt",
    "manifest.json",
    "RESULTS.md",
    "scientific-summary.json",
]
ROUNDTRIP_NAMES = ["execution-evidence.json", "launch-regressions.json"] + PROFILE_EVIDENCE
FETCH_NAMES = ["launch-receipt.json"] + ROUNDTRIP_NAMES
PHASES = [
    "authenticate-mirror-rehearsal-2004",
    "reproduce-published-output-roundtrip",
    "publish-bounded-mismatch-evidence",
]
ZERO_FIELDS = {
    "target_reads": 0,
    "candidate_reads": 0,
    "control_evaluations": 0,
    "new_scan_searches": 0,
    "new_jass_searches": 0,
    "fits": 0,
    "strength_games": 0,
    "selfplay_games": 0,
    "alpha_spent": 0,
    "promotions": 0,
    "bakes": 0,
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"not_object:{path.name}")
    return value


def compare_outputs(root: Path, proof: dict) -> tuple[dict[str, str], list[dict]]:
    expected = proof.get("output_sha256")
    if not isinstance(expected, dict) or set(expected) != set(ROUNDTRIP_NAMES):
        raise RuntimeError("receipt_output_hash_contract")
    actual = {name: published_output_sha(root / name, name) for name in ROUNDTRIP_NAMES}
    mismatches = []
    for name in ROUNDTRIP_NAMES:
        if actual[name] != expected[name]:
            mismatches.append({
                "path": name,
                "expected_sha256": expected[name],
                "actual_published_sha256": actual[name],
                "actual_raw_sha256": sha(root / name),
                "size_bytes": (root / name).stat().st_size,
            })
    return actual, mismatches


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    evidence = StageEvidence(artifact, mode)
    try:
        if mode != "rehearsal":
            raise RuntimeError("diagnostic_requires_rehearsal")
        artifact.mkdir(parents=True, exist_ok=True)
        recovered = result / "recovered-mirror-2004"

        evidence.begin(PHASES[0])
        selections = [("artefacts/" + name, name) for name in FETCH_NAMES]
        fetched = fetch_files(
            rclone="rclone",
            prefix=SOURCE_PREFIX,
            selections=selections,
            out_dir=recovered,
            expected_state="completed",
        )
        observed = (
            fetched.get("job_id"), fetched.get("attempt_id"), fetched.get("code_sha"),
            fetched.get("result_state"), fetched.get("exit_code"), fetched.get("host"),
        )
        if observed != (SOURCE_JOB, SOURCE_ATTEMPT, SOURCE_CODE_SHA, "completed", 0, "cpx62"):
            raise RuntimeError("source_2004_identity")
        if sha(recovered / "launch-receipt.json") != SOURCE_RECEIPT_SHA256:
            raise RuntimeError("source_2004_receipt_sha256")
        proof = read_json(recovered / "launch-receipt.json")
        if (
            proof.get("schema") != "jass.launch_receipt.v2"
            or proof.get("mode") != "rehearsal"
            or proof.get("verdict") != "REHEARSAL_EXECUTION_COMPLETE_V2"
            or proof.get("job_id") != SOURCE_JOB
            or proof.get("attempt_id") != SOURCE_ATTEMPT
            or proof.get("code_sha") != SOURCE_CODE_SHA
        ):
            raise RuntimeError("source_2004_launch_receipt_identity")
        evidence.complete()

        evidence.begin(PHASES[1])
        actual, mismatches = compare_outputs(recovered, proof)
        summary_value = read_json(recovered / "scientific-summary.json")
        scientific_summary_detail = {
            "expected_sha256": proof["output_sha256"]["scientific-summary.json"],
            "actual_published_sha256": actual["scientific-summary.json"],
            "actual_raw_sha256": sha(recovered / "scientific-summary.json"),
            "has_launch_decoration": "launch" in summary_value,
        }
        evidence.complete()

        evidence.begin(PHASES[2])
        diagnostic = {
            "schema": "jass.cls_mirror_2005_roundtrip_diagnostic.v1",
            "state": "completed",
            "classification": "TECHNICAL_DIAGNOSTIC_ONLY",
            "failed_production_job": "cpx62-2005-l3-cls-mirror-scale-production-v2",
            "failed_production_attempt": "20260916T133329Z-f769bc39",
            "failed_production_failure_code": "PUBLISHED_OUTPUT_ROUNDTRIP",
            "source_rehearsal_job": SOURCE_JOB,
            "source_rehearsal_attempt": SOURCE_ATTEMPT,
            "source_rehearsal_code_sha": SOURCE_CODE_SHA,
            "source_rehearsal_receipt_sha256": SOURCE_RECEIPT_SHA256,
            "roundtrip_names": ROUNDTRIP_NAMES,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
            "scientific_summary_detail": scientific_summary_detail,
            **ZERO_FIELDS,
            "scientific_verdict": None,
            "diagnostic_only": True,
            "next_stage": "PATCH_PROVEN_MECHANICAL_CAUSE_ONLY" if mismatches else "DIAGNOSE_GATE_CONTEXT_BEYOND_OUTPUT_HASHES",
        }
        atomic_json(artifact / "roundtrip-diagnostic.json", diagnostic)
        atomic_json(artifact / "scientific-summary.json", diagnostic)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.cls_mirror_2005_roundtrip_diagnostic_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            **ZERO_FIELDS,
            "scientific_verdict": None,
            "diagnostic_only": True,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
