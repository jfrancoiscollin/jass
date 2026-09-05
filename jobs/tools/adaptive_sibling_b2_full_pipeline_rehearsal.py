#!/usr/bin/env python3
"""Final target-host infrastructure rehearsal gate before B3.

This tool exercises one synthetic 4,000-parent B2 graph through:

native catalogue/verifier -> teacher merge -> allocation -> projection -> rich
readout -> the *production* R=200,000 statistical analyzer -> terminal report ->
production terminal publisher.

It runs no fresh source generation, no teacher search, no fit, no strength game,
no promotion and no bake. The synthetic fixture carries an internal preflight
runtime receipt; the tool records the actual target-host runtime separately and
uses the fixture runtime only for that synthetic receipt consistency check.

Only a complete success may emit ``FULL_PIPELINE_REHEARSAL_PASS``. This verdict
is an infrastructure readiness gate, never a scientific B2 policy verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Sequence
from unittest import mock

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tests.test_adaptive_sibling_b2_readout import terminal_pipeline_fixture  # noqa: E402
from jobs.tools import adaptive_sibling_b2_native_terminal_rehearsal as native  # noqa: E402
from jobs.tools import adaptive_sibling_b2_readout as readout  # noqa: E402
from jobs.tools import adaptive_sibling_b2_statistics as statistics  # noqa: E402
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b2_full_pipeline_rehearsal.v1"
PASS_VERDICT = "FULL_PIPELINE_REHEARSAL_PASS"
FAIL_VERDICT = "FULL_PIPELINE_REHEARSAL_FAIL"
EXPECTED_DRAWS = statistics.BOOTSTRAP_REPLICATIONS * statistics.PARENT_COUNT


class FullRehearsalError(RuntimeError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ) + "\n").encode("ascii")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def descriptor(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise FullRehearsalError(f"not a regular file: {path}")
    return {
        "local_name": resolved.name,
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FullRehearsalError(f"cannot read JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise FullRehearsalError(f"JSON root is not object: {path}")
    return value


def base_receipt() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": "INVALID",
        "verdict": FAIL_VERDICT,
        "scope": "target_host_full_pipeline_infrastructure_rehearsal",
        "actual_runtime": None,
        "native_build": None,
        "population": None,
        "statistics": None,
        "terminal": None,
        "publication": None,
        "error": None,
        "scientific_scope": {
            "fresh_data_reads": 0,
            "teacher_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "bakes": 0,
            "scientific_verdict": None,
        },
        "full_pipeline_rehearsal_pass": False,
        "b3_infrastructure_gate": "BLOCKED",
    }


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise FullRehearsalError(f"refusing existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FullRehearsalError(f"refusing existing temporary: {temporary}")
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
        if path.read_bytes() != raw:
            raise FullRehearsalError("output roundtrip mismatch")
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def run_full(work_dir: Path, log: io.StringIO) -> dict[str, object]:
    if work_dir.exists() or work_dir.is_symlink():
        raise FullRehearsalError("work directory must be absent")
    work_dir.mkdir(parents=True)
    build_dir = work_dir / "native-build"
    helper, verifier, native_build = native.build_native(build_dir, log)

    previous_helper = os.environ.get("JASS_B2_NATIVE_FIXTURE_HELPER")
    previous_verifier = os.environ.get("JASS_B2_NATIVE_VERIFIER")
    os.environ["JASS_B2_NATIVE_FIXTURE_HELPER"] = str(helper)
    os.environ["JASS_B2_NATIVE_VERIFIER"] = str(verifier)
    try:
        graph_dir = work_dir / "terminal-graph"
        (terminal_path, terminal_raw, terminal_manifest, fixture_runtime,
         _readout_manifest_path, _readout_manifest, merge_report) = \
            terminal_pipeline_fixture(graph_dir)

        groups_rows = merge_report["counters"]["groups_rows"]
        if merge_report["counters"]["parents"] != 4_000 \
                or merge_report["counters"]["shards"] != 16 \
                or type(groups_rows) is not int or groups_rows < 8_000:
            raise FullRehearsalError("native synthetic population mismatch")

        actual_runtime = statistics.runtime_environment()
        fixture_runtime_with_pid = {**fixture_runtime, "pid": os.getpid()}
        terminal_dir = work_dir / "terminal-output"
        started_statistics = time.monotonic()
        # The fixture contains a synthetic preflight receipt whose runtime is a
        # deterministic test value. Keep that internal binding coherent while
        # running the real production analyzer on the actual target host.
        with mock.patch.object(
                statistics, "runtime_environment",
                return_value=fixture_runtime_with_pid):
            readout.finalize_command(argparse.Namespace(
                input_manifest=terminal_path,
                expected_input_manifest_sha256=hashlib.sha256(terminal_raw).hexdigest(),
                out_dir=terminal_dir,
            ))
        statistics_seconds = time.monotonic() - started_statistics

        stats_path = terminal_dir / "b2-statistics-v1.json"
        terminal_report_path = terminal_dir / "b2-terminal-report-v1.json"
        progress_path = terminal_dir / "progress.json"
        stats = read_json(stats_path)
        terminal_report = read_json(terminal_report_path)
        progress = read_json(progress_path)

        if stats.get("schema") != statistics.OUTPUT_SCHEMA \
                or stats.get("status") != "VALID":
            raise FullRehearsalError("production statistics output invalid")
        stream = stats.get("bootstrap_stream")
        if type(stream) is not dict \
                or stream.get("accepted_draws") != EXPECTED_DRAWS:
            raise FullRehearsalError("production bootstrap draw count mismatch")
        if progress.get("completed_replications") != statistics.BOOTSTRAP_REPLICATIONS \
                or progress.get("total_replications") != statistics.BOOTSTRAP_REPLICATIONS:
            raise FullRehearsalError("production bootstrap progress incomplete")
        if not terminal_report.get("support", {}).get("all_valid"):
            raise FullRehearsalError("terminal support is not fully valid")
        if terminal_report.get("actions") != {
            "searches": 0, "fits": 0, "games": 0, "promotions": 0,
            "bakes": 0, "automatic_downstream_jobs": 0,
        }:
            raise FullRehearsalError("terminal action guard mismatch")

        artifact_dir = work_dir / "terminal-publication"
        publication = publisher.publish(
            input_manifest=terminal_path,
            expected_input_manifest_sha256=hashlib.sha256(terminal_raw).hexdigest(),
            terminal_dir=terminal_dir,
            code_sha=terminal_manifest["code_sha"],
            artifact_dir=artifact_dir,
        )
        if publication.get("byte_roundtrip_verified") is not True \
                or publication.get("automatic_downstream_jobs") != 0 \
                or publication.get("promotion_authorized") is not False \
                or publication.get("bake_authorized") is not False:
            raise FullRehearsalError("terminal publisher guard mismatch")

        return {
            "actual_runtime": actual_runtime,
            "native_build": native_build,
            "population": {
                "parents": 4_000,
                "shards": 16,
                "teacher_rows": groups_rows,
            },
            "statistics": {
                "tool": descriptor(ROOT / "jobs/tools/adaptive_sibling_b2_statistics.py"),
                "output": descriptor(stats_path),
                "progress": descriptor(progress_path),
                "replications": statistics.BOOTSTRAP_REPLICATIONS,
                "seed": statistics.BOOTSTRAP_SEED,
                "accepted_draws": stream["accepted_draws"],
                "elapsed_seconds": round(statistics_seconds, 6),
                "status": stats["status"],
            },
            "terminal": {
                "report": descriptor(terminal_report_path),
                "support_all_valid": True,
                "synthetic_terminal_verdict": terminal_report["verdict"],
            },
            "publication": {
                "receipt": descriptor(artifact_dir / "terminal-publication-receipt.json"),
                "byte_roundtrip_verified": True,
                "automatic_downstream_jobs": 0,
            },
        }
    finally:
        if previous_helper is None:
            os.environ.pop("JASS_B2_NATIVE_FIXTURE_HELPER", None)
        else:
            os.environ["JASS_B2_NATIVE_FIXTURE_HELPER"] = previous_helper
        if previous_verifier is None:
            os.environ.pop("JASS_B2_NATIVE_VERIFIER", None)
        else:
            os.environ["JASS_B2_NATIVE_VERIFIER"] = previous_verifier


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    resolved = [args.work_dir.resolve(), args.receipt.resolve(), args.log.resolve()]
    if len(set(resolved)) != len(resolved):
        print("work/receipt/log paths must differ", file=sys.stderr)
        return 2
    receipt = base_receipt()
    log = io.StringIO()
    started = time.monotonic()
    rc = 4
    try:
        outcome = run_full(args.work_dir, log)
        receipt.update(outcome)
        receipt["status"] = "VALID"
        receipt["verdict"] = PASS_VERDICT
        receipt["full_pipeline_rehearsal_pass"] = True
        receipt["b3_infrastructure_gate"] = "READY"
        rc = 0
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        log.write(receipt["error"] + "\n")
    receipt["duration_seconds"] = round(time.monotonic() - started, 6)
    try:
        write_new(args.log, log.getvalue().encode("utf-8"))
        write_new(args.receipt, canonical_json_bytes(receipt))
    except Exception as exc:
        print(f"adaptive_sibling_b2_full_pipeline_rehearsal: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({
        "schema": SCHEMA,
        "verdict": receipt["verdict"],
        "full_pipeline_rehearsal_pass": receipt["full_pipeline_rehearsal_pass"],
        "b3_infrastructure_gate": receipt["b3_infrastructure_gate"],
    }).decode("ascii"), end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
