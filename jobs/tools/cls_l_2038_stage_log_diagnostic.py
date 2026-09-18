#!/usr/bin/env python3
"""Recover bounded Launch-V2 stage logs for failed CLS-L fit rehearsal 2038.

The runner envelope proves only a quarantined TECHNICAL STAGE_FAILED:EXECUTE.
This diagnostic reads only runner-owned result-root stage stdout/stderr/receipt plus
the immutable failure envelope. It never reads CURRENT_2M/CURRICULUM payloads
or fitted model bytes and performs no fit, search, game, target read, alpha
spend, promotion or bake.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_2031_failure_diagnostic as base  # noqa: E402
from launch_runtime_v2 import StageEvidence, atomic_json as runtime_atomic_json  # noqa: E402

FAILED_JOB = "cpx62-2038-l3-cls-l-three-arm-fit-rehearsal-v2"
FAILED_ATTEMPT = "20260917T201315Z-d29e2c49"
FAILED_CODE = "d29e2c4985ffc77510f3fa91c51f640d89f37627"
FAILED_PREFIX = f"r2:jass-data/runs/{FAILED_JOB}/{FAILED_ATTEMPT}"
TERMINAL = "CLS_L_2038_STAGE_LOG_DIAGNOSTIC_COMPLETE_V1"
PHASE = "execute-cls-l-2038-stage-log-diagnostic"
MAX_BYTES = 2 * 1024 * 1024
STAGE_LOG_ALLOWLIST = (
    "stage.stdout.log",
    "stage.stderr.log",
    "stage-receipt.json",
)


def stage_log_selections(verified: dict) -> list[tuple[str, str]]:
    inventory = {item.get("path"): item for item in verified.get("files", [])}
    selected: list[tuple[str, str]] = []
    for remote in STAGE_LOG_ALLOWLIST:
        item = inventory.get(remote)
        if not item:
            continue
        size = int(item.get("size_bytes", 0))
        if 0 < size <= MAX_BYTES:
            selected.append((remote, "stage-logs/" + remote))
    return selected


def summarize_stage_logs(root: Path, selections: list[tuple[str, str]]) -> dict[str, object]:
    logs: list[dict[str, object]] = []
    errors: list[str] = []
    aborts: list[str] = []
    for remote, local in selections:
        path = root / local
        parsed = base.bounded_lines(path.read_text(encoding="utf-8", errors="replace"), 60)
        errors.extend(f"{remote}: {line}" for line in parsed["error_lines"])
        if parsed["last_abort"]:
            aborts.append(f"{remote}: {parsed['last_abort']}")
        logs.append({
            "remote_path": remote,
            "sha256": base.sha256(path),
            "size_bytes": path.stat().st_size,
            "bounded_output": parsed,
        })
    primary = aborts[-1] if aborts else (errors[-1] if errors else None)
    return {
        "logs": logs,
        "error_lines": errors[-24:],
        "last_abort": aborts[-1] if aborts else None,
        "primary_mechanical_error": primary,
    }


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    work = result_dir / "work" / "failed-2038-stage-logs"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    evidence.begin(PHASE)

    rclone = os.environ.get("RCLONE_BIN", "rclone")
    verified = base.fetch.inspect_result_inventory(
        rclone=rclone, prefix=FAILED_PREFIX, expected_state="failed"
    )
    if (
        verified.get("job_id") != FAILED_JOB
        or verified.get("attempt_id") != FAILED_ATTEMPT
        or verified.get("code_sha") != FAILED_CODE
        or verified.get("result_state") != "failed"
        or int(verified.get("exit_code", 0)) == 0
    ):
        raise RuntimeError("failed-2038 identity/state drift")

    envelope = base.fetch.fetch_files(
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
    selections = stage_log_selections(verified)
    if selections:
        base.fetch.fetch_files(
            rclone=rclone,
            prefix=FAILED_PREFIX,
            expected_state="failed",
            selections=selections,
            out_dir=work,
        )

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    attempt = json.loads((work / "attempt-diagnostic.json").read_text(encoding="utf-8"))
    if manifest.get("job_id") != FAILED_JOB or manifest.get("attempt_id") != FAILED_ATTEMPT:
        raise RuntimeError("failed manifest identity drift")
    if attempt.get("classification") != "TECHNICAL" or attempt.get("scientific_verdict") is not None:
        raise RuntimeError("2038 was not a quarantined technical failure")

    stage_logs = summarize_stage_logs(work, selections)
    stage_inventory = [
        item.get("path")
        for item in verified.get("files", [])
        if isinstance(item.get("path"), str) and item["path"].startswith("stage")
    ]
    diagnostic = {
        "schema": "jass.cls_l_2038_stage_log_diagnostic.v1",
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
            "manifest_sha256": base.sha256(work / "manifest.json"),
        },
        "authenticated_stage_inventory_paths": stage_inventory,
        "bounded_stage_logs": stage_logs,
        "boundary": {
            "historical_training_payloads_read": 0,
            "fitted_model_payloads_read": 0,
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
    write_json(art / "failure-evidence.json", diagnostic)
    write_json(
        art / "source-authentication.json",
        {
            "schema": "jass.cls_l_2038_stage_log_authentication.v1",
            "authenticated": True,
            "job_id": FAILED_JOB,
            "attempt_id": FAILED_ATTEMPT,
            "code_sha": FAILED_CODE,
            "result_state": "failed",
            "exit_code": manifest.get("exit_code"),
            "selected_envelope_files": envelope.get("files"),
            "selected_stage_log_paths": [remote for remote, _ in selections],
            "inventory_authenticated": True,
        },
    )
    primary = stage_logs["primary_mechanical_error"]
    summary = {
        "schema": "jass.cls_l_2038_stage_log_diagnostic_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "selected_stage_log_paths": [remote for remote, _ in selections],
        "authenticated_stage_inventory_paths": stage_inventory,
        "last_abort": stage_logs["last_abort"],
        "primary_mechanical_error": primary,
        "bounded_stage_error_lines": stage_logs["error_lines"][-12:],
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "REPAIR_PROVEN_2038_MECHANICS_ONLY" if primary else "RECOVER_PRE_STAGE_LAUNCHER_EVIDENCE",
    }
    runtime_atomic_json(art / "scientific-summary.json", summary)
    write_json(
        art / "manifest.json",
        {
            "schema": "jass.cls_l_2038_stage_log_diagnostic_manifest.v1",
            "terminal": TERMINAL,
            "failed_job_id": FAILED_JOB,
            "failed_attempt_id": FAILED_ATTEMPT,
            "diagnostic_only": True,
            "scientific_payloads_read": 0,
            "fitted_model_payloads_read": 0,
            "bounded_stage_logs_read": len(selections),
        },
    )
    (art / "RESULTS.md").write_text(
        f"# CLS-L 2038 stage-log diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- failed attempt: `{FAILED_JOB}` / `{FAILED_ATTEMPT}`\n"
        f"- selected stage logs: `{[remote for remote, _ in selections]}`\n"
        f"- primary mechanical error: `{primary}`\n"
        "- scientific/model payload reads/fits/searches/games/alpha/promotion/bake: 0\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
