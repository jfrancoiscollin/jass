#!/usr/bin/env python3
"""Run one stage and expose its compact receipt through the GitOps allowlist.

The core stage runner remains authoritative. This bridge adds observability only:
- delegates execution to ``run_experiment_stage.run_stage``;
- writes a compact ``scientific-summary.json`` when the stage did not already
  publish one;
- writes ``attempt-diagnostic.json`` on failure when absent.

Both filenames are already allowlisted by runner-v3 for small JSON summaries,
so failure_class/failure_stage/spec identity become visible in jass-control
without copying logs or arbitrary outputs into Git.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import run_experiment_stage as core  # noqa: E402

SUMMARY_SCHEMA = "jass.stage_status_summary.v1"
DIAGNOSTIC_SCHEMA = "jass.stage_failure_diagnostic.v1"


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ) + "\n").encode("ascii")


def write_new(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(payload)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError(f"refusing existing temporary output: {temporary}")
    temporary.write_bytes(raw)
    os.replace(temporary, path)
    if path.read_bytes() != raw:
        raise RuntimeError(f"summary roundtrip mismatch: {path}")


def compact_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": SUMMARY_SCHEMA,
        "job_id": os.environ.get("JASS_JOB_ID"),
        "attempt_id": os.environ.get("JASS_ATTEMPT_ID"),
        "campaign": receipt.get("campaign"),
        "stage": receipt.get("stage"),
        "code_sha": receipt.get("code_sha"),
        "spec_sha256": receipt.get("spec_sha256"),
        "state": receipt.get("state"),
        "failure_class": receipt.get("failure_class"),
        "failure_stage": receipt.get("failure_stage"),
        "error": receipt.get("error"),
        "exit_code": receipt.get("exit_code"),
        "timed_out": receipt.get("timed_out"),
        "inputs_authenticated": receipt.get("inputs_authenticated"),
        "outputs_authenticated": receipt.get("outputs_authenticated"),
        "declared_scientific_side_effects": receipt.get(
            "declared_scientific_side_effects"
        ),
        "next_stage": receipt.get("next_stage"),
        "scientific_verdict": None,
    }


def failure_diagnostic(receipt: Mapping[str, Any]) -> dict[str, Any]:
    summary = compact_summary(receipt)
    return {
        "schema": DIAGNOSTIC_SCHEMA,
        "classification": "stage_runner_failure",
        **{key: value for key, value in summary.items() if key != "schema"},
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    rc, receipt = core.run_stage(
        spec_path=args.spec,
        repo_root=args.repo_root,
        result_dir=args.result_dir,
        artifact_dir=args.artifact_dir,
    )
    artifact_dir = args.artifact_dir.resolve()
    try:
        write_new(artifact_dir / "scientific-summary.json", compact_summary(receipt))
        if rc != 0:
            write_new(
                artifact_dir / "attempt-diagnostic.json",
                failure_diagnostic(receipt),
            )
    except Exception as exc:
        print(f"run_experiment_stage_status_bridge: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({
        "schema": SUMMARY_SCHEMA,
        "state": receipt.get("state"),
        "failure_class": receipt.get("failure_class"),
        "failure_stage": receipt.get("failure_stage"),
        "next_stage": receipt.get("next_stage"),
    }).decode("ascii"), end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
