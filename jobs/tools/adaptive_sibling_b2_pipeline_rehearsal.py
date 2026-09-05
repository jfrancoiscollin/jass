#!/usr/bin/env python3
"""Run the Level-1 synthetic contract rehearsal for the frozen B2 pipeline.

This is infrastructure validation, not a scientific B2 rerun. It consumes no
fresh source, teacher score, fit, strength game, promotion, or bake. The suite
binds the real B2 producer/consumer contract tests behind one fail-closed
receipt. A target-host stage-spec rehearsal is still required before the
stronger ``FULL_PIPELINE_REHEARSAL_PASS`` gate may be claimed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest
from typing import Sequence

SCHEMA = "jass.adaptive_sibling_b2_synthetic_pipeline_rehearsal.v1"
PASS_VERDICT = "B2_SYNTHETIC_CONTRACT_REHEARSAL_PASS"
FAIL_VERDICT = "B2_SYNTHETIC_CONTRACT_REHEARSAL_FAIL"

MODULES = (
    "jobs.tests.test_adaptive_sibling_b2_legacy_contract_compat",
    "jobs.tests.test_adaptive_sibling_b2_teacher_preread",
    "jobs.tests.test_adaptive_sibling_b2_teacher_source",
    "jobs.tests.test_adaptive_sibling_b2_teacher_merge",
    "jobs.tests.test_adaptive_sibling_b2_publisher_contracts",
    "jobs.tests.test_adaptive_sibling_b2_allocation_input",
    "jobs.tests.test_adaptive_sibling_b2_readout",
    "jobs.tests.test_adaptive_sibling_b2_terminal_publish",
)


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


def _module_descriptor(name: str) -> dict[str, object]:
    module = importlib.import_module(name)
    path = Path(module.__file__).resolve(strict=True)
    return {
        "module": name,
        "local_name": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def build_suite() -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for name in MODULES:
        suite.addTests(loader.loadTestsFromName(name))
    return suite


def run_rehearsal() -> tuple[dict[str, object], str]:
    started = time.monotonic()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(build_suite())
    duration = time.monotonic() - started
    failures = [test.id() for test, _trace in result.failures]
    errors = [test.id() for test, _trace in result.errors]
    unexpected = [test.id() for test in getattr(result, "unexpectedSuccesses", [])]
    skipped = [test.id() for test, _reason in result.skipped]
    passed = result.wasSuccessful() and not unexpected and result.testsRun > 0
    receipt = {
        "schema": SCHEMA,
        "status": "VALID" if passed else "INVALID",
        "verdict": PASS_VERDICT if passed else FAIL_VERDICT,
        "scope": "synthetic_contract_rehearsal_only",
        "modules": [_module_descriptor(name) for name in MODULES],
        "tests_run": result.testsRun,
        "failures": failures,
        "errors": errors,
        "unexpected_successes": unexpected,
        "skipped": skipped,
        "duration_seconds": round(duration, 6),
        "runtime": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
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
        "next_gate": "TARGET_HOST_STAGE_SPEC_REHEARSAL",
    }
    return receipt, stream.getvalue()


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise RuntimeError(f"refusing existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError(f"refusing existing temporary: {temporary}")
    try:
        temporary.write_bytes(raw)
        temporary.replace(path)
        if path.read_bytes() != raw:
            raise RuntimeError("output roundtrip mismatch")
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.receipt.resolve() == args.log.resolve():
        print("receipt and log paths must differ", file=sys.stderr)
        return 2
    try:
        receipt, log = run_rehearsal()
        write_new(args.log, log.encode("utf-8"))
        write_new(args.receipt, canonical_json_bytes(receipt))
    except Exception as exc:
        print(f"adaptive_sibling_b2_pipeline_rehearsal: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({
        "schema": SCHEMA,
        "verdict": receipt["verdict"],
        "tests_run": receipt["tests_run"],
        "next_gate": receipt["next_gate"],
    }).decode("ascii"), end="")
    return 0 if receipt["verdict"] == PASS_VERDICT else 4


if __name__ == "__main__":
    raise SystemExit(main())
