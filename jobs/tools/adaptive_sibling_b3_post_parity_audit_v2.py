#!/usr/bin/env python3
"""B3 post-parity audit v2: semantic parsing for generic fetch reports.

The v1 scientific/authentication checks remain unchanged.  This wrapper replaces
only the 1833 fetch-report boundary: `fetch_result_files.py --report` owns an
indented semantic JSON serialization, so its fields are authenticated without
requiring compact canonical bytes.  The four fetched scientific artefacts
continue to be checked by v1 with their strict canonical-byte contracts.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b3_post_parity_audit as v1  # noqa: E402


class SemanticFetchReportError(v1.AuditError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SemanticFetchReportError(f"duplicate fetch-report JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise SemanticFetchReportError(f"invalid fetch-report JSON constant: {value}")


def read_semantic_fetch_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=_reject_duplicates,
                           parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticFetchReportError(f"invalid semantic fetch report {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise SemanticFetchReportError(f"fetch report root is not an object: {path.name}")
    return value


def fetch_parity_artifacts(work: Path) -> dict[str, Path]:
    out = work / "parity-terminal"
    report = work / "parity-terminal-fetch.json"
    names = (
        "b3-real-adaptive-parity.json",
        "b3-teacher-aggregate.json",
        "b3-render-receipt.json",
        "scientific-summary.json",
    )
    argv = [sys.executable, "jobs/tools/fetch_result_files.py",
            "--prefix", v1.PARITY_PREFIX, "--expected-state", "completed",
            "--out-dir", str(out), "--report", str(report)]
    for name in names:
        argv += ["--file", f"artefacts/{name}={name}"]
    v1.run(argv)
    receipt = read_semantic_fetch_report(report)
    required = {
        "state": "verified",
        "result_state": "completed",
        "job_id": v1.PARITY_JOB,
        "attempt_id": v1.PARITY_ATTEMPT,
        "code_sha": v1.PARITY_CODE,
        "prefix": v1.PARITY_PREFIX,
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise SemanticFetchReportError(f"1833 fetch receipt {key} mismatch")
    return {name: out / name for name in names}


def main(argv: Sequence[str] | None = None) -> int:
    v1.fetch_parity_artifacts = fetch_parity_artifacts
    return v1.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
