#!/usr/bin/env python3
"""Validate and publish fail-closed JFI Boundary-A facts without running a fit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ZERO_MARKERS = {
    "FULL_FITS": 0,
    "FRESH_OPENINGS": 0,
    "STRENGTH_GAMES": 0,
    "SCIENTIFIC_DECISION": False,
    "SCAN_WEIGHT_READS": 0,
    "SCAN_SCORE_READS": 0,
}


def build_facts(source):
    if source.get("schema") != "jass.jfi.boundary_a_input.v1":
        raise ValueError("unexpected Boundary-A input schema")
    markers = source.get("markers")
    if markers != ZERO_MARKERS:
        raise ValueError(f"Boundary-A zero markers mismatch: {markers!r}")
    code_sha = source.get("code_sha")
    if not isinstance(code_sha, str) or len(code_sha) != 40:
        raise ValueError("code_sha must be a full 40-character Git SHA")
    machine = source.get("machine", {})
    if (machine.get("host") != "cpx62" or int(machine.get("nproc", 0)) != 16
            or machine.get("avx2") is not True or machine.get("bmi2") is not True
            or machine.get("native_build") is not True):
        raise ValueError("CPX62 AVX2/BMI2-native machine contract drift")
    disk = source.get("disk", {})
    if (int(disk.get("code_free_bytes", 0)) <= 0
            or int(disk.get("scratch_free_bytes", 0)) <= 0):
        raise ValueError("code/scratch free-disk facts are required")
    current = source.get("current_2m", {})
    if current.get("records") != 2_000_000:
        raise ValueError("CURRENT_2M must authenticate exactly 2,000,000 records")
    if current.get("split_seed") != 577215:
        raise ValueError("CURRENT_2M split seed drift")
    if not current.get("sha256") or not source.get("context30", {}).get("sha256"):
        raise ValueError("CURRENT_2M and Context30 hashes are required")
    sizer = source.get("sizer", {})
    rows = int(sizer.get("rows", 0))
    iterations = int(sizer.get("iterations", 0))
    seconds = float(sizer.get("seconds", 0.0))
    if not 0 < rows <= 20_000 or not 0 < iterations <= 2 or seconds <= 0:
        raise ValueError("sizer must be bounded to <=20,000 rows and <=2 iterations")
    fit_timeout = int(sizer.get("full_fit_timeout_seconds", 0))
    if fit_timeout <= 0:
        raise ValueError("full-fit timeout fact is required")
    train_rows = int(current.get("train_records", 0))
    if not 0 < train_rows < current["records"]:
        raise ValueError("invalid authenticated train/holdout counts")
    seconds_per_iteration = seconds / iterations
    # The streamed full-batch implementation scales primarily with rows per pass.
    projected_arm_seconds = seconds_per_iteration * train_rows / rows * 2000
    facts = {
        "schema": "jass.jfi.boundary_a_facts.v1",
        "verdict": "JFI_BOUNDARY_A_READY",
        "code_sha": code_sha,
        "machine": machine,
        "numeric_env": source.get("numeric_env"),
        "disk": disk,
        "current_2m": current,
        "context30": source.get("context30"),
        "feature_dump": source.get("feature_dump"),
        "sizer": {
            **sizer,
            "role": "bounded_preflight_no_full_fit",
            "projected_seconds_per_2000_iteration_arm": projected_arm_seconds,
            "projected_seconds_seven_physical_arms": projected_arm_seconds * 7,
            "full_fit_timeout_seconds": fit_timeout,
        },
        "markers": ZERO_MARKERS,
        "next_boundary": "GO JFI FIT",
    }
    return facts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    facts = build_facts(source)
    Path(args.out).write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("JFI_BOUNDARY_A_READY FULL_FITS=0 FRESH_OPENINGS=0 STRENGTH_GAMES=0 "
          "SCIENTIFIC_DECISION=FALSE SCAN_WEIGHT_READS=0 SCAN_SCORE_READS=0")
    print("NEXT_BOUNDARY = GO JFI FIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
