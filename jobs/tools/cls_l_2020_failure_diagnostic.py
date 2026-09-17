#!/usr/bin/env python3
"""Bounded technical diagnostic for failed CLS-L normalization preflight 2020.

Reads only the immutable failed runner-v3 envelope plus an explicit allowlist of
small stage work logs. It never reads CURRENT_2M/CURRICULUM training payloads,
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
    r"ABORT(?: line=|:)|Traceback|error:|error\b|failed|usage:|No such file|CMake Error|ninja:|make(?:\[|:)|mismatch|drift",
    re.IGNORECASE,
)
WORK_LOG_MAX_BYTES = 2 * 1024 * 1024
WORK_LOG_ALLOWLIST = (
    "work/RESULTS.md",
    "work/fetch-abc.log",
    "work/fetch-turnover.log",
    "work/fetch-curriculum.log",
    "work/split.log",
    "work/gen8.log",
    "work/cmake.log",
    "work/build.log",
    "work/features.log",
    "work/normalization.log",
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


def bounded_work_log_selections(verified: dict) -> list[tuple[str, str]]:
    """Select only preregistered small textual work logs from authenticated inventory."""
    inventory = {item.get("path"): item for item in verified.get("files", [])}
    selected: list[tuple[str, str]] = []
    for remote in WORK_LOG_ALLOWLIST:
        item = inventory.get(remote)
        if not item:
            continue
        size = int(item.get("size_bytes", 0))
        if size <= 0 or size > WORK_LOG_MAX_BYTES:
            continue
        local = "worklogs/" + remote.removeprefix("work/").replace("/", "_")
        selected.append((remote, local))
    return selected


def summarize_work_logs(root: Path, selections: list[tuple[str, str]]) -> dict[str, object]:
    logs = []
    error_lines: list[str] = []
    aborts: list[str] = []
    for remote, local in selections:
        path = root / local
        parsed = bounded_lines(path.read_text(encoding="utf-8", errors="replace"), limit=40)
        tagged_errors = [f"{remote}: {line}" for line in parsed["error_lines"]]
        error_lines.extend(tagged_errors)
        if parsed["last_abort"]:
            aborts.append(f"{remote}: {parsed['last_abort']}")
        logs.append({
            "remote_path": remote,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "bounded_output": parsed,
        })
    primary = aborts[-1] if aborts else (error_lines[-1] if error_lines else None)
    return {
        "logs": logs,
        "error_lines": error_lines[-24:],
        "last_abort": aborts[-1] if aborts else None,
        "primary_mechanical_error": primary,
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

    rclone = os.environ.get("RCLONE_BIN", "rclone")
    verified = fetch.inspect_result_inventory(
        rclone=rclone,
        prefix=FAILED_PREFIX,
        expected_state="failed",
    )
    if (
        verified.get("job_id") != FAILED_JOB
        or verified.get("attempt_id") != FAILED_ATTEMPT
        or verified.get("code_sha") != FAILED_CODE
        or verified.get("result_state") != "failed"
        or int(verified.get("exit_code", 0)) == 0
    ):
        raise RuntimeError("failed-2020 identity/state drift")

    report = fetch.fetch_files(
        rclone=rclone,
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
    work_log_selections = bounded_work_log_selections(verified)
    if work_log_selections:
        fetch.fetch_files(
            rclone=rclone,
            prefix=FAILED_PREFIX,
            expected_state="failed",
            selections=work_log_selections,
            out_dir=work,
        )

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    attempt = json.loads((work / "attempt-diagnostic.json").read_text(encoding="utf-8"))
    runner_launch = json.loads((work / "runner-launch.json").read_text(encoding="utf-8"))
    if manifest.get("job_id") != FAILED_JOB or manifest.get("attempt_id") != FAILED_ATTEMPT:
        raise RuntimeError("failed manifest identity drift")
    if attempt.get("classification") != "TECHNICAL" or attempt.get("scientific_verdict") is not None:
        raise RuntimeError("2020 was not a quarantined technical failure")

    parsed = bounded_lines(read_gzip(work / "output.log.gz"))
    work_logs = summarize_work_logs(work, work_log_selections)
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
        "bounded_work_logs": work_logs,
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
        "selected_envelope_files": report.get("files"),
        "selected_work_log_paths": [remote for remote, _ in work_log_selections],
        "inventory_authenticated": True,
    })
    summary = {
        "schema": "jass.cls_l_2020_failure_diagnostic_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "last_abort": work_logs["last_abort"] or parsed["last_abort"],
        "primary_mechanical_error": work_logs["primary_mechanical_error"],
        "bounded_work_log_paths": [remote for remote, _ in work_log_selections],
        "bounded_work_log_error_lines": work_logs["error_lines"][-12:],
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
    runtime_atomic_json(art / "scientific-summary.json", summary)
    atomic_json(art / "manifest.json", {
        "schema": "jass.cls_l_2020_failure_diagnostic_manifest.v1",
        "terminal": TERMINAL,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "diagnostic_only": True,
        "scientific_payloads_read": 0,
        "bounded_work_logs_read": len(work_log_selections),
    })
    (art / "RESULTS.md").write_text(
        "# CLS-L 2020 technical failure diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- failed attempt: `{FAILED_JOB}` / `{FAILED_ATTEMPT}`\n"
        f"- last shell abort: `{summary['last_abort']}`\n"
        f"- primary mechanical error: `{summary['primary_mechanical_error']}`\n"
        "- scientific payload reads/fits/searches/games/alpha/promotion/bake: 0\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
