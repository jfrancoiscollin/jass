#!/usr/bin/env python3
"""Build native B2 helpers and rehearse the 4000-parent chain to terminal publish.

Infrastructure only. The real native move catalogue/verifier, merge, allocation,
projection, rich readout, terminal authentication and terminal publisher are
exercised. The expensive production R=200000 statistical analyzer is *not* run;
the dedicated integration test replaces it with one bounded deterministic call.
Therefore this tool cannot claim FULL_PIPELINE_REHEARSAL_PASS. Its next gate is
the production-statistics target-host rehearsal.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "jass.adaptive_sibling_b2_native_terminal_rehearsal.v1"
PASS_VERDICT = "B2_NATIVE_TERMINAL_REHEARSAL_PASS"
FAIL_VERDICT = "B2_NATIVE_TERMINAL_REHEARSAL_FAIL"
TEST_ID = (
    "jobs.tests.test_adaptive_sibling_b2_native_terminal_rehearsal."
    "NativeTerminalRehearsalTests.test_native_4000_pipeline_reaches_terminal_publisher"
)
CXX_CACHE_RE = re.compile(r"CMAKE_CXX_COMPILER:FILEPATH=(.+)\Z")


class RehearsalError(RuntimeError):
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
        raise RehearsalError(f"not a regular file: {path}")
    return {
        "local_name": resolved.name,
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def run_command(
    command: Sequence[str], *, cwd: Path, log: io.StringIO, timeout: int,
) -> None:
    log.write("$ " + " ".join(command) + "\n")
    completed = subprocess.run(
        list(command), cwd=str(cwd), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False,
    )
    log.write(completed.stdout)
    if completed.returncode != 0:
        raise RehearsalError(
            f"command failed rc={completed.returncode}: {' '.join(command)}")


def cmake_compiler(cache: Path) -> Path:
    for line in cache.read_text(encoding="utf-8", errors="strict").splitlines():
        match = CXX_CACHE_RE.fullmatch(line)
        if match:
            path = Path(match.group(1))
            if path.is_file():
                return path.resolve(strict=True)
    raise RehearsalError("CMAKE_CXX_COMPILER missing from CMakeCache.txt")


def locate_static_library(build_dir: Path) -> Path:
    matches = list(build_dir.rglob("libjass_lib.a"))
    if len(matches) != 1:
        raise RehearsalError(f"expected one libjass_lib.a, got {len(matches)}")
    return matches[0].resolve(strict=True)


def locate_verifier(build_dir: Path) -> Path:
    candidates = [
        build_dir / "jass_adaptive_sibling_b2_teacher_merge_verify",
        build_dir / "jass_adaptive_sibling_b2_teacher_merge_verify.exe",
    ]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        raise RehearsalError(f"expected one native verifier, got {len(matches)}")
    return matches[0].resolve(strict=True)


def build_native(build_dir: Path, log: io.StringIO) -> tuple[Path, Path, dict[str, object]]:
    if build_dir.exists() or build_dir.is_symlink():
        raise RehearsalError("native rehearsal build directory must be absent")
    cmake = shutil.which("cmake")
    if not cmake:
        raise RehearsalError("cmake not found")
    cmake = str(Path(cmake).resolve(strict=True))
    run_command([
        cmake, "-S", str(ROOT), "-B", str(build_dir),
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_NATIVE=OFF",
        "-DJASS_ENABLE_SIMD=OFF",
    ], cwd=ROOT, log=log, timeout=180)
    run_command([
        cmake, "--build", str(build_dir), "--target",
        "jass_adaptive_sibling_b2_teacher_merge_verify", "--parallel", "2",
    ], cwd=ROOT, log=log, timeout=600)

    verifier = locate_verifier(build_dir)
    library = locate_static_library(build_dir)
    compiler = cmake_compiler(build_dir / "CMakeCache.txt")
    fixture_source = ROOT / "jobs/tests/fixtures/adaptive_sibling_b2_native_fixture.cpp"
    helper = build_dir / "adaptive_sibling_b2_native_fixture"
    compile_command = [
        str(compiler), "-std=c++20", "-O2", "-I", str(ROOT / "src"),
        str(fixture_source), str(library), "-pthread", "-o", str(helper),
    ]
    run_command(compile_command, cwd=ROOT, log=log, timeout=300)
    if not helper.is_file():
        raise RehearsalError("native fixture helper was not produced")
    if os.name != "nt":
        helper.chmod(0o755)
    build = {
        "cmake": descriptor(Path(cmake)),
        "compiler": descriptor(compiler),
        "jass_lib": descriptor(library),
        "fixture_source": descriptor(fixture_source),
        "fixture_helper": descriptor(helper),
        "native_verifier": descriptor(verifier),
        "configure": {
            "build_type": "Release",
            "JASS_NATIVE": False,
            "JASS_ENABLE_SIMD": False,
        },
    }
    return helper.resolve(strict=True), verifier, build


def run_test(helper: Path, verifier: Path, log: io.StringIO) -> dict[str, object]:
    previous_helper = os.environ.get("JASS_B2_NATIVE_FIXTURE_HELPER")
    previous_verifier = os.environ.get("JASS_B2_NATIVE_VERIFIER")
    os.environ["JASS_B2_NATIVE_FIXTURE_HELPER"] = str(helper)
    os.environ["JASS_B2_NATIVE_VERIFIER"] = str(verifier)
    stream = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(TEST_ID)
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        if previous_helper is None:
            os.environ.pop("JASS_B2_NATIVE_FIXTURE_HELPER", None)
        else:
            os.environ["JASS_B2_NATIVE_FIXTURE_HELPER"] = previous_helper
        if previous_verifier is None:
            os.environ.pop("JASS_B2_NATIVE_VERIFIER", None)
        else:
            os.environ["JASS_B2_NATIVE_VERIFIER"] = previous_verifier
    log.write(stream.getvalue())
    skipped = [test.id() for test, _reason in result.skipped]
    failures = [test.id() for test, _trace in result.failures]
    errors = [test.id() for test, _trace in result.errors]
    if result.testsRun != 1 or skipped or failures or errors or not result.wasSuccessful():
        raise RehearsalError(
            f"native terminal test failed: run={result.testsRun} skipped={skipped} "
            f"failures={failures} errors={errors}")
    return {
        "tests_run": result.testsRun,
        "test_id": TEST_ID,
        "skipped": skipped,
        "failures": failures,
        "errors": errors,
    }


def base_receipt() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": "INVALID",
        "verdict": FAIL_VERDICT,
        "scope": "native_synthetic_terminal_rehearsal_only",
        "build": None,
        "tests": None,
        "error": None,
        "scientific_scope": {
            "fresh_data_reads": 0,
            "teacher_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "bakes": 0,
            "production_bootstrap_replications": 0,
            "scientific_verdict": None,
        },
        "full_pipeline_rehearsal_pass": False,
        "next_gate": "PRODUCTION_STATISTICS_TARGET_HOST_REHEARSAL",
    }


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise RehearsalError(f"refusing existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RehearsalError(f"refusing existing temporary: {temporary}")
    try:
        temporary.write_bytes(raw)
        os.replace(temporary, path)
        if path.read_bytes() != raw:
            raise RehearsalError("output roundtrip mismatch")
    except BaseException:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    resolved = [args.build_dir.resolve(), args.receipt.resolve(), args.log.resolve()]
    if len(set(resolved)) != len(resolved):
        print("build/receipt/log paths must differ", file=sys.stderr)
        return 2
    receipt = base_receipt()
    log = io.StringIO()
    started = time.monotonic()
    rc = 4
    try:
        helper, verifier, build = build_native(args.build_dir, log)
        receipt["build"] = build
        receipt["tests"] = run_test(helper, verifier, log)
        receipt["status"] = "VALID"
        receipt["verdict"] = PASS_VERDICT
        rc = 0
    except Exception as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        log.write(receipt["error"] + "\n")
    receipt["duration_seconds"] = round(time.monotonic() - started, 6)
    try:
        write_new(args.log, log.getvalue().encode("utf-8"))
        write_new(args.receipt, canonical_json_bytes(receipt))
    except Exception as exc:
        print(f"adaptive_sibling_b2_native_terminal_rehearsal: {exc}", file=sys.stderr)
        return 2
    print(canonical_json_bytes({
        "schema": SCHEMA,
        "verdict": receipt["verdict"],
        "next_gate": receipt["next_gate"],
    }).decode("ascii"), end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
