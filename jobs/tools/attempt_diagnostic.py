#!/usr/bin/env python3
"""Classify a runner-v3 duplicate-attempt failure without changing science."""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path


SIGNALS = (
    ("oom_kill", re.compile(r"out of memory|oom-kill|killed process", re.I)),
    ("disk_full", re.compile(r"no space left on device|enospc", re.I)),
    ("private_tmp_teardown", re.compile(r"private.?tmp|/tmp.*no such file|enoent", re.I)),
    ("explicit_kill", re.compile(r"kill-in-flight|sigterm|terminated by request", re.I)),
    ("process_signal", re.compile(r"signal 9|sigkill|killed|terminated", re.I)),
)


def read_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8", errors="replace")


def matching_lines(text: str, pattern: re.Pattern, limit: int = 12) -> list[str]:
    result = []
    for line in text.splitlines():
        if pattern.search(line):
            result.append(line[-500:])
            if len(result) >= limit:
                break
    return result


def diagnose(
    success: dict,
    failed: dict,
    *,
    failed_log: str = "",
    journal: str = "",
    kernel: str = "",
) -> dict:
    corpus = "\n".join((failed_log, journal, kernel))
    evidence = {}
    probable = None
    for name, pattern in SIGNALS:
        lines = matching_lines(corpus, pattern)
        if lines:
            evidence[name] = lines
            if probable is None:
                probable = name

    failed_exit = int(failed.get("exit_code", -1))
    if probable is None and failed_exit == -1:
        probable = "wrapper_lost_without_exit_status"
    elif probable is None:
        probable = "job_failed_nonzero"

    same_job = success.get("job_id") == failed.get("job_id")
    same_code = success.get("code_sha") == failed.get("code_sha")
    authoritative_success = (
        success.get("state") == "completed"
        and int(success.get("exit_code", -1)) == 0
    )
    duplicate_failed = failed.get("state") == "failed" and failed_exit != 0
    return {
        "schema": 1,
        "experiment": "runner-attempt-diagnostic",
        "successful_attempt": {
            key: success.get(key)
            for key in ("job_id", "attempt_id", "code_sha", "host", "state", "exit_code")
        },
        "failed_attempt": {
            key: failed.get(key)
            for key in ("job_id", "attempt_id", "code_sha", "host", "state", "exit_code")
        },
        "same_job": same_job,
        "same_code_sha": same_code,
        "probable_cause": probable,
        "evidence": evidence,
        "scientific_result_preserved": bool(
            authoritative_success and duplicate_failed and same_job
        ),
        "decision": "investigate_infrastructure",
        "replay_science_required": not bool(
            authoritative_success and duplicate_failed and same_job
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--success-manifest", type=Path, required=True)
    parser.add_argument("--failed-manifest", type=Path, required=True)
    parser.add_argument("--failed-log", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = diagnose(
        json.loads(args.success_manifest.read_text(encoding="utf-8")),
        json.loads(args.failed_manifest.read_text(encoding="utf-8")),
        failed_log=read_text(args.failed_log),
        journal=read_text(args.journal),
        kernel=read_text(args.kernel),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
