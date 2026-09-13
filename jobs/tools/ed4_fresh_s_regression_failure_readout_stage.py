#!/usr/bin/env python3
"""Read only the runner-owned launch regression diagnostics from failed S rehearsal 1939."""
from __future__ import annotations

# CI retrigger after automatic incident-ledger update; diagnostic inputs unchanged.
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import fetch_result_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SOURCE_JOB = "cpx62-1939-l3-ed4-fresh-s-source-rehearsal-v1"
SOURCE_ATTEMPT = "20260913T160656Z-04011fd1"
SOURCE_CODE = "04011fd1c7321021ef0df844517512ef9fa08795"
SOURCE_PREFIX = f"r2:jass-data/runs/{SOURCE_JOB}/{SOURCE_ATTEMPT}"
PHASES = ["authenticate-failed-attempt", "read-launch-regression-diagnostics", "publish-technical-readout"]
DIAGNOSTIC_PATHS = ("launch-regressions.json", "launch-regressions.log")
MAX_LOG_TAIL = 16384


def fetch_diagnostics(out_dir: Path):
    report = fetch_result_files.inspect_result_inventory(
        rclone="rclone", prefix=SOURCE_PREFIX, expected_state="failed",
    )
    identity = (
        report.get("job_id"), report.get("attempt_id"), report.get("code_sha"),
        report.get("result_state"), report.get("exit_code"),
    )
    if identity != (SOURCE_JOB, SOURCE_ATTEMPT, SOURCE_CODE, "failed", 2):
        raise RuntimeError("failed_attempt_identity")
    files = {item["path"]: item for item in report["files"]}
    for name in DIAGNOSTIC_PATHS:
        item = files.get(name)
        if item is None or item.get("size_bytes", -1) <= 0:
            raise RuntimeError(f"missing_or_empty_regression_diagnostic:{name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in DIAGNOSTIC_PATHS:
        item = files[name]
        fetch_result_files.base.download_verified(
            "rclone", SOURCE_PREFIX + "/" + name, out_dir / name,
            item["sha256"], item["size_bytes"],
        )
    return report


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    evidence = StageEvidence(artifact, os.environ["LAUNCH_MODE"])
    try:
        evidence.begin(PHASES[0])
        out = result / "s-1939-regression-readout"
        fetch_diagnostics(out)
        evidence.complete()

        evidence.begin(PHASES[1])
        regressions = json.loads((out / "launch-regressions.json").read_text(encoding="utf-8"))
        if regressions.get("schema") != "jass.launch_regressions.v2":
            raise RuntimeError("regression_report_schema")
        raw = (out / "launch-regressions.log").read_bytes()
        diagnostic = {
            "schema": "jass.ed4.fresh_s_regression_failure_readout.v1",
            "state": "completed",
            "classification": "TECHNICAL_DIAGNOSTIC_ONLY",
            "source_job_id": SOURCE_JOB,
            "source_attempt_id": SOURCE_ATTEMPT,
            "source_code_sha": SOURCE_CODE,
            "regressions": regressions,
            "regression_log_tail": raw[-MAX_LOG_TAIL:].decode("utf-8", errors="replace"),
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
        atomic_json(artifact / "ed4-fresh-s-regression-failure-readout.json", diagnostic)
        summary = dict(diagnostic)
        summary["next_stage"] = "ED4_FRESH_S_TECHNICAL_REPAIR_FROM_AUTHENTICATED_1939_REGRESSION_LOG"
        atomic_json(artifact / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return 0
    except Exception as exc:
        evidence.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.fresh_s_regression_failure_readout_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "scientific_verdict": None,
            "confirmation_authorized": False,
            "target_reads": 0,
            "alpha_spent": 0,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
