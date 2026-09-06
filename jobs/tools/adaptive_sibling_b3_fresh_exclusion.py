#!/usr/bin/env python3
"""Build the authenticated B3 fresh-corpus exclusion universe.

This is a technical preparation stage only. It combines the already-frozen
historical B2 exclusion union with the 4,000 target-blind B2 confirmation parent
identities. It reads no teacher score/label and generates no fresh B3 parent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools.adaptive_sibling_b2_exclusions import (  # noqa: E402
    canonical_fingerprint,
    canonical_json_bytes,
    sha256_file,
)

SCHEMA = "jass.adaptive_sibling_b3_fresh_exclusion_preparation.v1"
MANIFEST_SCHEMA = "jass.adaptive_sibling_b3_fresh_exclusion_manifest.v1"
VERDICT = "B3_FRESH_EXCLUSION_PREPARATION_COMPLETE"
CANONICALIZATION = "min(exact,rotate180_plus_colour_swap_and_invert_stm)"
HISTORICAL_COUNT = 223_317
B2_COUNT = 4_000
COMBINED_COUNT = HISTORICAL_COUNT + B2_COUNT

HISTORICAL = {
    "job_id": "cpx62-1773-l3-decision-math-b2-historical-identities-v1",
    "attempt_id": "20260905T012244Z-1490b353",
    "code_sha": "1490b3536f6943ec5eab62578ea7d42a29395a27",
    "prefix": "r2:jass-data/runs/cpx62-1773-l3-decision-math-b2-historical-identities-v1/20260905T012244Z-1490b353",
    "manifest_remote": "artefacts/historical-parent-exclusion-manifest.json",
    "manifest_sha256": "2f1a551bf6fe020e6436689dc8ef8c95940f473d79a2ebc8613e6c15447cff16",
    "union_remote": "artefacts/historical-parent-canonical-union.txt",
    "union_sha256": "3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f",
}
B2 = {
    "job_id": "cpx62-1778-l3-decision-math-b2-source-selection-v1",
    "attempt_id": "20260905T102917Z-d3657332",
    "code_sha": "d3657332c3a5609a5501a9ff130f5d5c19488c7f",
    "prefix": "r2:jass-data/runs/cpx62-1778-l3-decision-math-b2-source-selection-v1/20260905T102917Z-d3657332",
    "publication_remote": "artefacts/source-selection-publication.json",
    "publication_sha256": "e61339f1edba4f22e29a9b02b1d1708d426a27626b0f58ea789ea6c5f946cca1",
    "identities_remote": "artefacts/ordered-identities.txt",
}


class StageError(RuntimeError):
    pass


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise StageError(f"not a regular file: {path}")
    return {"local_name": path.name, "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size, **extra}


def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise StageError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise StageError(f"refusing existing temporary {tmp}")
    try:
        tmp.write_bytes(raw)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def run(argv: Sequence[str], *, cwd: Path = ROOT, timeout: int = 600) -> None:
    completed = subprocess.run(list(argv), cwd=str(cwd), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if completed.returncode != 0:
        tail = completed.stdout.decode(errors="replace")[-8000:]
        raise StageError(f"command failed rc={completed.returncode}: {' '.join(argv)}\n{tail}")


def fetch(prefix: str, identity: Mapping[str, str], files: Sequence[tuple[str, str]],
          out_dir: Path, report: Path, *, rclone_bin: str) -> dict[str, Any]:
    argv = [sys.executable, "jobs/tools/fetch_result_files.py", "--prefix", prefix,
            "--expected-state", "completed", "--out-dir", str(out_dir),
            "--report", str(report), "--rclone-bin", rclone_bin]
    for remote, local in files:
        argv += ["--file", f"{remote}={local}"]
    run(argv)
    value = json.loads(report.read_text(encoding="utf-8"))
    expected = {"state": "verified", "result_state": "completed", "exit_code": 0,
                "job_id": identity["job_id"], "attempt_id": identity["attempt_id"],
                "code_sha": identity["code_sha"], "prefix": prefix}
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            raise StageError(f"fetch receipt {key} mismatch")
    return value


def canonical_lines(path: Path, *, expected_count: int, require_sorted: bool) -> list[str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise StageError(f"identity file is not canonical LF text: {path.name}")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise StageError("identity file is not ASCII") from exc
    if len(lines) != expected_count or len(set(lines)) != expected_count:
        raise StageError(f"identity cardinality mismatch for {path.name}")
    previous = ""
    for line in lines:
        if not line or canonical_fingerprint(line) != line:
            raise StageError(f"non-canonical identity in {path.name}")
        if require_sorted and line <= previous:
            raise StageError(f"identity file not sorted unique: {path.name}")
        previous = line
    return lines


def verify_historical(manifest: Path, union: Path) -> list[str]:
    if sha256_file(manifest) != HISTORICAL["manifest_sha256"]:
        raise StageError("historical manifest SHA mismatch")
    if sha256_file(union) != HISTORICAL["union_sha256"]:
        raise StageError("historical union SHA mismatch")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    checks = {
        "schema": "jass.adaptive_sibling_b2_historical_exclusion_manifest.v1",
        "universe": "PR771_B2_V1_HISTORICAL_40",
        "union_unique_canonical": HISTORICAL_COUNT,
        "union_sha256": HISTORICAL["union_sha256"],
        "canonicalization": CANONICALIZATION,
        "scores_or_labels_read": 0,
    }
    for key, wanted in checks.items():
        if value.get(key) != wanted:
            raise StageError(f"historical manifest {key} mismatch")
    return canonical_lines(union, expected_count=HISTORICAL_COUNT, require_sorted=True)


def verify_b2(publication: Path, identities: Path) -> list[str]:
    if sha256_file(publication) != B2["publication_sha256"]:
        raise StageError("B2 source publication SHA mismatch")
    value = json.loads(publication.read_text(encoding="utf-8"))
    if value.get("schema") != "jass.adaptive_sibling_b2_source_selection_publication.v1" \
            or value.get("verdict") != "B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE":
        raise StageError("B2 publication schema/verdict mismatch")
    selection = value.get("selection")
    if not isinstance(selection, dict) or selection.get("parents") != B2_COUNT \
            or selection.get("forbidden_overlap") != 0 or selection.get("target_blind") is not True:
        raise StageError("B2 selection contract mismatch")
    expected = selection.get("ordered_identities")
    actual = descriptor(identities, rows=B2_COUNT,
                        serialization="canonical_fingerprint_ascii, one per line, LF terminated")
    if not isinstance(expected, dict) or any(expected.get(k) != actual[k]
                                             for k in ("sha256", "size_bytes", "rows", "serialization")):
        raise StageError("B2 ordered identities descriptor mismatch")
    return canonical_lines(identities, expected_count=B2_COUNT, require_sorted=False)


def combine(historical: Iterable[str], b2: Iterable[str]) -> tuple[list[str], int]:
    old = set(historical)
    new = set(b2)
    overlap = len(old & new)
    if overlap != 0:
        raise StageError(f"B2/historical exclusion overlap is nonzero: {overlap}")
    combined = sorted(old | new)
    if len(combined) != COMBINED_COUNT:
        raise StageError(f"combined exclusion cardinality mismatch: {len(combined)}")
    return combined, overlap


def execute(work: Path, artifacts: Path, *, rclone_bin: str) -> dict[str, object]:
    if work.exists() or work.is_symlink():
        raise StageError("work directory must be absent")
    work.mkdir(parents=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    hist_dir = work / "historical"
    b2_dir = work / "b2"
    fetch(HISTORICAL["prefix"], HISTORICAL,
          [(HISTORICAL["manifest_remote"], "historical-manifest.json"),
           (HISTORICAL["union_remote"], "historical-union.txt")],
          hist_dir, work / "historical-fetch.json", rclone_bin=rclone_bin)
    fetch(B2["prefix"], B2,
          [(B2["publication_remote"], "b2-source-publication.json"),
           (B2["identities_remote"], "b2-ordered-identities.txt")],
          b2_dir, work / "b2-fetch.json", rclone_bin=rclone_bin)

    historical = verify_historical(hist_dir / "historical-manifest.json",
                                   hist_dir / "historical-union.txt")
    b2 = verify_b2(b2_dir / "b2-source-publication.json",
                   b2_dir / "b2-ordered-identities.txt")
    combined, overlap = combine(historical, b2)

    union_path = artifacts / "b3-fresh-exclusion-union.txt"
    union_raw = ("\n".join(combined) + "\n").encode("ascii")
    write_new(union_path, union_raw)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "universe": "DECISION_INFORMATION_B3_FRESH_V1_EXCLUSION",
        "canonicalization": CANONICALIZATION,
        "components": [
            {"kind": "historical_b1_b2_exclusion", "job_id": HISTORICAL["job_id"],
             "attempt_id": HISTORICAL["attempt_id"], "count": HISTORICAL_COUNT,
             "sha256": HISTORICAL["union_sha256"]},
            {"kind": "b2_confirmation_parents", "job_id": B2["job_id"],
             "attempt_id": B2["attempt_id"], "count": B2_COUNT,
             "publication_sha256": B2["publication_sha256"],
             "ordered_identities_sha256": sha256_file(b2_dir / "b2-ordered-identities.txt")},
        ],
        "component_overlap": overlap,
        "union_unique_canonical": COMBINED_COUNT,
        "union_sha256": hashlib.sha256(union_raw).hexdigest(),
        "scores_or_labels_read": 0,
        "fresh_b3_parents_generated": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    manifest_path = artifacts / "b3-fresh-exclusion-manifest.json"
    write_new(manifest_path, canonical_json_bytes(manifest))
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "historical_count": HISTORICAL_COUNT,
        "b2_count": B2_COUNT,
        "component_overlap": overlap,
        "combined_count": COMBINED_COUNT,
        "combined_union_sha256": manifest["union_sha256"],
        "combined_manifest_sha256": sha256_file(manifest_path),
        "teacher_searches": 0,
        "fresh_b3_parents": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "B3_FRESH_ADAPTIVE_CORPUS_PREREGISTRATION",
    }
    summary_path = artifacts / "scientific-summary.json"
    write_new(summary_path, canonical_json_bytes(summary))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--rclone-bin", default="/usr/bin/rclone")
    args = parser.parse_args(argv)
    try:
        summary = execute(args.work_dir, args.artifact_dir, rclone_bin=args.rclone_bin)
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_exclusion: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
