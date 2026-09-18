#!/usr/bin/env python3
"""Recover the bounded inner fit.log from failed CLS-L rehearsal 2038.

This is technical-diagnostic only. It authenticates the immutable failed 2038
runner publication, fetches only artefacts/logs.tar.gz plus the failure envelope,
and extracts only the regular file named fit.log. No corpus, target, fitted model,
search/game result, alpha, promotion or bake payload is read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tarfile

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
TERMINAL = "CLS_L_2038_FIT_LOG_DIAGNOSTIC_COMPLETE_V1"
PHASE = "execute-cls-l-2038-fit-log-diagnostic"
ARCHIVE_REMOTE = "artefacts/logs.tar.gz"
ARCHIVE_MAX_BYTES = 2 * 1024 * 1024
FIT_LOG_MAX_BYTES = 2 * 1024 * 1024


def write_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise RuntimeError(f"no-clobber:{path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def archive_selection(verified: dict) -> tuple[str, str]:
    inventory = {item.get("path"): item for item in verified.get("files", [])}
    item = inventory.get(ARCHIVE_REMOTE)
    if not item:
        raise RuntimeError("2038 logs.tar.gz absent from authenticated inventory")
    size = int(item.get("size_bytes", 0))
    if size <= 0 or size > ARCHIVE_MAX_BYTES:
        raise RuntimeError(f"2038 logs.tar.gz size outside bound:{size}")
    return ARCHIVE_REMOTE, "logs.tar.gz"


def extract_fit_log(archive: Path, out: Path) -> dict[str, object]:
    matches = []
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            if Path(member.name).name == "fit.log":
                matches.append(member)
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one fit.log, found {len(matches)}")
        member = matches[0]
        if not member.isfile():
            raise RuntimeError("fit.log is not a regular file")
        if member.size <= 0 or member.size > FIT_LOG_MAX_BYTES:
            raise RuntimeError(f"fit.log size outside bound:{member.size}")
        handle = tf.extractfile(member)
        if handle is None:
            raise RuntimeError("fit.log cannot be extracted")
        raw = handle.read(FIT_LOG_MAX_BYTES + 1)
    if len(raw) > FIT_LOG_MAX_BYTES:
        raise RuntimeError("fit.log exceeds bounded extraction limit")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    parsed = base.bounded_lines(raw.decode("utf-8", errors="replace"), 120)
    primary = parsed["last_abort"] or (parsed["error_lines"][-1] if parsed["error_lines"] else None)
    return {
        "archive_member": member.name,
        "size_bytes": len(raw),
        "sha256": base.sha256(out),
        "bounded_output": parsed,
        "primary_mechanical_error": primary,
    }


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    work = result_dir / "work" / "failed-2038-fit-log"
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
            ("artefacts/attempt-diagnostic.json", "attempt-diagnostic.json"),
            ("artefacts/runner-launch.json", "runner-launch.json"),
        ],
        out_dir=work,
    )
    remote, local = archive_selection(verified)
    archive_fetch = base.fetch.fetch_files(
        rclone=rclone,
        prefix=FAILED_PREFIX,
        expected_state="failed",
        selections=[(remote, local)],
        out_dir=work,
    )

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    attempt = json.loads((work / "attempt-diagnostic.json").read_text(encoding="utf-8"))
    if manifest.get("job_id") != FAILED_JOB or manifest.get("attempt_id") != FAILED_ATTEMPT:
        raise RuntimeError("failed manifest identity drift")
    if attempt.get("classification") != "TECHNICAL" or attempt.get("scientific_verdict") is not None:
        raise RuntimeError("2038 was not a quarantined technical failure")

    fit_log = extract_fit_log(work / "logs.tar.gz", work / "fit.log")
    primary = fit_log["primary_mechanical_error"]
    if not primary:
        raise RuntimeError("fit.log contained no bounded mechanical error")

    diagnostic = {
        "schema": "jass.cls_l_2038_fit_log_diagnostic.v1",
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
        "fit_log": fit_log,
        "boundary": {
            "historical_training_payloads_read": 0,
            "targets_read": 0,
            "fitted_model_payloads_read": 0,
            "fits": 0,
            "new_jass_searches": 0,
            "new_scan_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        },
    }
    write_json(art / "fit-log-evidence.json", diagnostic)
    write_json(
        art / "source-authentication.json",
        {
            "schema": "jass.cls_l_2038_fit_log_authentication.v1",
            "authenticated": True,
            "job_id": FAILED_JOB,
            "attempt_id": FAILED_ATTEMPT,
            "code_sha": FAILED_CODE,
            "result_state": "failed",
            "exit_code": manifest.get("exit_code"),
            "selected_envelope_files": envelope.get("files"),
            "selected_archive_files": archive_fetch.get("files"),
            "selected_archive_member": fit_log["archive_member"],
        },
    )
    summary = {
        "schema": "jass.cls_l_2038_fit_log_diagnostic_summary.v1",
        "terminal": TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": FAILED_JOB,
        "failed_attempt_id": FAILED_ATTEMPT,
        "fit_log_sha256": fit_log["sha256"],
        "primary_mechanical_error": primary,
        "bounded_fit_error_lines": fit_log["bounded_output"]["error_lines"][-16:],
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "REPAIR_PROVEN_2038_FIT_MECHANICS_ONLY",
    }
    runtime_atomic_json(art / "scientific-summary.json", summary)
    write_json(
        art / "manifest.json",
        {
            "schema": "jass.cls_l_2038_fit_log_diagnostic_manifest.v1",
            "terminal": TERMINAL,
            "failed_job_id": FAILED_JOB,
            "failed_attempt_id": FAILED_ATTEMPT,
            "diagnostic_only": True,
            "scientific_payloads_read": 0,
            "fitted_model_payloads_read": 0,
            "archive_member_read": fit_log["archive_member"],
        },
    )
    (art / "RESULTS.md").write_text(
        f"# CLS-L 2038 inner fit-log diagnostic\n\n"
        f"- terminal: `{TERMINAL}`\n"
        f"- failed attempt: `{FAILED_JOB}` / `{FAILED_ATTEMPT}`\n"
        f"- bounded member: `{fit_log['archive_member']}`\n"
        f"- primary mechanical error: `{primary}`\n"
        "- corpus/targets/models/fits/searches/games/alpha/promotion/bake: 0\n",
        encoding="utf-8",
    )
    evidence.complete()
    evidence.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
