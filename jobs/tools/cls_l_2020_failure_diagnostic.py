#!/usr/bin/env python3
"""Bounded technical diagnostic for failed CLS-L normalization preflight 2020.

Reads only the immutable failed runner-v3 envelope (manifest/output log and
Launch-V2 failure artefacts). It never reads CURRENT_2M/CURRICULUM training data,
performs no fit/search/game, and publishes no scientific conclusion.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import fetch_result_files as fetch  # noqa: E402
from launch_runtime_v2 import StageEvidence, atomic_json as runtime_atomic_json  # noqa: E402

FAILED_JOB = "cpx62-2020-l3-cls-l-source-normalization-preflight-v2"
FAILED_ATTEMPT = "20260917T023839Z-68301b10"
FAILED_CODE = "68301b1027ef37e3c829eccadd42f4ba9cb86ce9"
FAILED_PREFIX = f"r2:jass-data/runs/{FAILED_JOB}/{FAILED_ATTEMPT}"
TERMINAL = "CLS_L_2020_TECHNICAL_DIAGNOSTIC_COMPLETE_V1"
PHASE = "execute-cls-l-2020-failure-diagnostic"
ERROR_RE = re.compile(
    r"ABORT(?: line=|:)|Traceback|error:|error\b|failed|usage:|No such file|CMake Error|ninja:|make(?:\[|:)",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_gzip(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        return stream.read()


def bounded_lines(text: str, limit: int = 80) -> dict[str, object]:
    lines = text.splitlines()
    matches = [line[-1000:] for line in lines if ERROR_RE.search(line)]
    aborts = [line[-1000:] for line in lines if "ABORT line=" in line or line.startswith("ABORT:")]
    return {
        "line_count": len(lines),
        "tail": [line[-1000:] for line in lines[-limit:]],
        "error_lines": matches[-limit:],
        "last_abort": aborts[-1] if aborts else None,
    }


def atomic_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    work = result_dir / "work" / "failed-2020"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    evidence.begin(PHASE)

    report = fetch.fetch_files(
        rclone=os.environ.get("RCLONE_BIN", "rclone"),
        prefix=FAILED_PREFIX,
        expected_state="failed",
        selections=[
            ("manifest.json", "manifest.json"),
            ("output.log.gz", "output.log.gz"),
            ("artefacts/attempt-diagnostic.json", "attempt-diagnostic.json"),
            ("artefacts/runner-launch.json", "runner-launch.json"),
        ],
        out_dir=work,
    )
    if (
        report.get("job_id") != FAILED_JOB
        or report.get("attempt_id") != FAILED_ATTEMPT
        or report.get("code_sha") != FAILED_CODE
        or report.get("result_state") != "failed"
        or int(report.get("exit_code", 0)) == 0
    ):
        raise RuntimeError("failed-2020 identity/state drift")

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    attempt = json.loads((work / "attempt-diagnostic.json").read_text(encoding="utf-8"))
    runner_launch = json.loads((work / "runner-launch.json").read_text(encoding="utf-8"))
    if manifest.get("job_id") != FAILED_JOB or manifest.get("attempt_id") != FAILED_ATTEMPT:
        raise RuntimeError("failed manifest identity drift")
    if attempt.get("classification") != "TECHNICAL" or attempt.get("scientific_verdict") is not None:
        raise RuntimeError("2020 was not a quarantined technical failure")

    parsed = bounded_lines(read_gzip(work / "output.log.gz"))
    diagnostic = {
        "schema": "jass.cls_l_2020_failure_diagnostic.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_source": {
            "job_id": FAILED_JOB,
            "attempt_id": FAILED_ATTEMPT,
            "code_sha": FAILED_CODE,
            "exit_code": manifest.get("exit_code"),
            "failure_code": attempt.get("failure_code"),
            "manifest_sha256": sha256(work / "manifest.json"),
            "output_log_sha256": sha256(work / "output.log.gz"),
            "runner_launch_sha256": sha256(work / "runner-launch.json"),
        },
        "bounded_output": parsed,
        "runner_launch": runner_launch,
        "boundary": {
            "historical_training_payloads_read": 0,
            "fits": 0,
            "new_jass_searches": 0,
            "new_scan_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "confirmation_target_reads": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        },
    }
    atomic_json(art / "failure-evidence.json", diagnostic)
    atomic_json(art / "source-authentication.json", {
        "schema": "jass.cls_l_2020_failed_source_authentication.v1",
        "authenticated": True,
        "job_id": FAILED_JOB,
        "attempt_id": FAILED_ATTEMPT,
        "code_sha": FAILED_CODE,
        "result_state": "failed",
        "exit_code": manifest.get("exit_code"),
        "selected_files": report.get("files"),
    })
    summary = {
        "schema": "jass.cls_l_2020_failure_diagnostic_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "last_abort": parsed["last_abort"],
        "bounded_error_lines": parsed["error_lines"][-12:],
        "bounded_tail": parsed["tail"][-12:],
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "REPAIR_PROVEN_2020_MECHANICS_ONLY",
    }
    # StageEvidence owns the progress summary while the stage is running. Replace
    # only that transport/progress record with the final diagnostic summary.
    runtime_atomic_json(art / "scientific-summary.json", summary)
    atomic_json(art / "manifest.json", {
        "schema": "jass.cls_l_2020_failure_diagnostic_manifest.v1",
        "terminal": TERMINAL,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "diagnostic_only": True,
        "scientific_payloads_read": 0,
    })
    (art / "RESULTS.md").write_text(
        "# CLS-L 2020 technical failure diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- failed attempt: `{FAILED_JOB}` / `{FAILED_ATTEMPT}`\n"
        f"- last shell abort: `{parsed['last_abort']}`\n"
        "- scientific payload reads/fits/searches/games/alpha/promotion/bake: 0\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
