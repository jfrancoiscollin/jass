#!/usr/bin/env python3
"""Prepare the immutable exclusion universe for the first fresh B3 corpus.

This preflight reads only already-consumed identity evidence: the B1/historical
canonical union and the published B2 4,000-parent ordered identities.  It does
not generate fresh positions and performs no teacher search, fit, game,
promotion or bake.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools.adaptive_sibling_b2_exclusions import parse_fingerprint  # noqa: E402

HISTORICAL_JOB = "cpx62-1773-l3-decision-math-b2-historical-identities-v1"
HISTORICAL_ATTEMPT = "20260905T012244Z-1490b353"
HISTORICAL_CODE = "1490b3536f6943ec5eab62578ea7d42a29395a27"
HISTORICAL_PREFIX = f"r2:jass-data/runs/{HISTORICAL_JOB}/{HISTORICAL_ATTEMPT}"
HISTORICAL_UNION_SHA256 = "3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f"
HISTORICAL_UNIQUE = 223_317

B2_JOB = "cpx62-1778-l3-decision-math-b2-source-selection-v1"
B2_ATTEMPT = "20260905T102917Z-d3657332"
B2_CODE = "d3657332c3a5609a5501a9ff130f5d5c19488c7f"
B2_PREFIX = f"r2:jass-data/runs/{B2_JOB}/{B2_ATTEMPT}"
B2_PARENTS = 4_000

EXPECTED_COMBINED_UNIQUE = HISTORICAL_UNIQUE + B2_PARENTS
SUCCESS_VERDICT = "B3_FRESH_EXCLUSION_UNION_READY_V1"


class ExclusionPrepareError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_canonical_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExclusionPrepareError(f"invalid JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ExclusionPrepareError(f"non-canonical JSON {path.name}")
    return value


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ExclusionPrepareError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise ExclusionPrepareError(f"refusing existing temporary {tmp}")
    try:
        tmp.write_bytes(raw)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def canonical_identity_lines(path: Path, *, expected_rows: int | None = None) -> list[str]:
    raw = path.read_bytes()
    if not raw or b"\r" in raw or not raw.endswith(b"\n"):
        raise ExclusionPrepareError(f"identity file is not LF-terminated: {path.name}")
    try:
        text = raw.decode("ascii")
    except UnicodeError as exc:
        raise ExclusionPrepareError(f"identity file is not ASCII: {path.name}") from exc
    lines = text.splitlines()
    if expected_rows is not None and len(lines) != expected_rows:
        raise ExclusionPrepareError(
            f"identity row count mismatch {path.name}: {len(lines)} != {expected_rows}")
    if not lines or any(not line for line in lines) or len(set(lines)) != len(lines):
        raise ExclusionPrepareError(f"identity file is empty/duplicate: {path.name}")
    for line in lines:
        try:
            parse_fingerprint(line)
        except Exception as exc:  # contract helper uses a typed ValueError-like exception
            raise ExclusionPrepareError(f"invalid canonical fingerprint in {path.name}") from exc
    return lines


def validate_b2_publication(receipt: dict[str, Any], identities: Path) -> dict[str, Any]:
    if receipt.get("schema") != "jass.adaptive_sibling_b2_source_selection_publication.v1":
        raise ExclusionPrepareError("B2 publication schema mismatch")
    if receipt.get("status") != "VALID" or receipt.get("verdict") != "B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE":
        raise ExclusionPrepareError("B2 source selection is not terminal VALID")
    implementation = receipt.get("implementation")
    if not isinstance(implementation, dict) or implementation.get("commit") != B2_CODE:
        raise ExclusionPrepareError("B2 publication implementation mismatch")
    selection = receipt.get("selection")
    if not isinstance(selection, dict) or selection.get("parents") != B2_PARENTS:
        raise ExclusionPrepareError("B2 publication parent count mismatch")
    if selection.get("forbidden_overlap") != 0 or selection.get("target_blind") is not True:
        raise ExclusionPrepareError("B2 source selection exclusion/target-blind contract mismatch")
    descriptor = selection.get("ordered_identities")
    if not isinstance(descriptor, dict):
        raise ExclusionPrepareError("B2 ordered identity descriptor missing")
    expected = {
        "local_name": "ordered-identities.txt",
        "sha256": sha256_file(identities),
        "size_bytes": identities.stat().st_size,
        "rows": B2_PARENTS,
        "serialization": "canonical_fingerprint_ascii, one per line, LF terminated",
    }
    if descriptor != expected:
        raise ExclusionPrepareError("B2 ordered identity descriptor mismatch")
    return descriptor


def build_combined_union(historical: Iterable[str], b2: Iterable[str]) -> tuple[bytes, dict[str, int]]:
    historical_set = set(historical)
    b2_set = set(b2)
    overlap = historical_set & b2_set
    if overlap:
        raise ExclusionPrepareError(f"B2 identities overlap historical universe: {len(overlap)}")
    if len(historical_set) != HISTORICAL_UNIQUE:
        raise ExclusionPrepareError("historical unique count mismatch")
    if len(b2_set) != B2_PARENTS:
        raise ExclusionPrepareError("B2 unique count mismatch")
    combined = historical_set | b2_set
    if len(combined) != EXPECTED_COMBINED_UNIQUE:
        raise ExclusionPrepareError("combined unique count mismatch")
    raw = ("\n".join(sorted(combined)) + "\n").encode("ascii")
    return raw, {
        "historical_unique": len(historical_set),
        "b2_unique": len(b2_set),
        "cross_overlap": 0,
        "combined_unique": len(combined),
    }


def fetch(prefix: str, expected_job: str, expected_attempt: str, expected_code: str,
          mappings: list[tuple[str, str]], out_dir: Path, report: Path) -> None:
    argv = [sys.executable, "jobs/tools/fetch_result_files.py", "--prefix", prefix,
            "--expected-state", "completed", "--out-dir", str(out_dir),
            "--report", str(report)]
    for remote, local in mappings:
        argv.extend(["--file", f"{remote}={local}"])
    completed = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False, timeout=600)
    if completed.returncode != 0:
        raise ExclusionPrepareError(
            "authenticated fetch failed: " + completed.stdout.decode(errors="replace")[-4000:])
    value = read_canonical_json(report)
    required = {
        "state": "verified", "result_state": "completed", "job_id": expected_job,
        "attempt_id": expected_attempt, "code_sha": expected_code, "prefix": prefix,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise ExclusionPrepareError(f"fetch receipt {key} mismatch")


def run(work_dir: Path, artifact_dir: Path) -> dict[str, Any]:
    if work_dir.exists() or work_dir.is_symlink():
        raise ExclusionPrepareError("work-dir must not exist")
    work_dir.mkdir(parents=True)
    if artifact_dir.is_symlink():
        raise ExclusionPrepareError("artifact-dir cannot be a symlink")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    hist = work_dir / "historical"
    b2 = work_dir / "b2"
    fetch(HISTORICAL_PREFIX, HISTORICAL_JOB, HISTORICAL_ATTEMPT, HISTORICAL_CODE,
          [("artefacts/historical-parent-canonical-union.txt", "historical-union.txt")],
          hist, work_dir / "historical-fetch.json")
    historical_path = hist / "historical-union.txt"
    if sha256_file(historical_path) != HISTORICAL_UNION_SHA256:
        raise ExclusionPrepareError("historical union SHA mismatch")

    fetch(B2_PREFIX, B2_JOB, B2_ATTEMPT, B2_CODE,
          [("artefacts/source-selection-publication.json", "source-selection-publication.json"),
           ("artefacts/ordered-identities.txt", "ordered-identities.txt")],
          b2, work_dir / "b2-fetch.json")
    b2_ids_path = b2 / "ordered-identities.txt"
    receipt = read_canonical_json(b2 / "source-selection-publication.json")
    descriptor = validate_b2_publication(receipt, b2_ids_path)

    historical_ids = canonical_identity_lines(historical_path, expected_rows=HISTORICAL_UNIQUE)
    b2_ids = canonical_identity_lines(b2_ids_path, expected_rows=B2_PARENTS)
    combined_raw, counts = build_combined_union(historical_ids, b2_ids)

    union_path = artifact_dir / "b3-fresh-exclusion-union.txt"
    write_new(union_path, combined_raw)
    manifest = {
        "schema": "jass.adaptive_sibling_b3_fresh_exclusion_manifest.v1",
        "canonicalization": "min(exact,rotate180_plus_colour_swap_and_invert_stm)",
        "sources": {
            "historical": {
                "job_id": HISTORICAL_JOB, "attempt_id": HISTORICAL_ATTEMPT,
                "code_sha": HISTORICAL_CODE, "sha256": HISTORICAL_UNION_SHA256,
                "unique_canonical": HISTORICAL_UNIQUE,
            },
            "b2": {
                "job_id": B2_JOB, "attempt_id": B2_ATTEMPT, "code_sha": B2_CODE,
                "ordered_identities": descriptor,
            },
        },
        "counts": counts,
        "union": {
            "local_name": union_path.name,
            "sha256": sha256_bytes(combined_raw),
            "size_bytes": len(combined_raw),
            "unique_canonical": EXPECTED_COMBINED_UNIQUE,
            "serialization": "canonical_fingerprint_ascii, sorted unique, LF terminated",
        },
        "fresh_targets_read": 0,
        "fresh_positions_generated": 0,
        "teacher_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "status": "VALID",
        "verdict": SUCCESS_VERDICT,
    }
    manifest_path = artifact_dir / "b3-fresh-exclusion-manifest.json"
    write_new(manifest_path, canonical_json(manifest))
    summary = {
        "schema": "jass.adaptive_sibling_b3_fresh_exclusion_summary.v1",
        "state": "completed",
        "verdict": SUCCESS_VERDICT,
        "combined_unique": EXPECTED_COMBINED_UNIQUE,
        "historical_unique": HISTORICAL_UNIQUE,
        "b2_unique": B2_PARENTS,
        "cross_overlap": 0,
        "fresh_b3_generation_authorized": False,
        "next_stage": "B3_FRESH_CORPUS_PREREGISTRATION_FREEZE",
        "new_teacher_searches": 0,
        "fresh_data_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    write_new(artifact_dir / "scientific-summary.json", canonical_json(summary))
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        summary = run(args.work_dir, args.artifact_dir)
    except (ExclusionPrepareError, OSError, subprocess.SubprocessError) as exc:
        print(f"adaptive_sibling_b3_exclusion_prepare: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
