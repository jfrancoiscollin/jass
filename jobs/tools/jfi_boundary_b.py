#!/usr/bin/env python3
"""Validate JFI Boundary-B facts and stop before full active selection/fits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ZERO_MARKERS = {
    "JFI_C_FULL_FITS": 0,
    "TARGET_READS_BEFORE_SELECTION_FREEZE": 0,
    "FRESH_OPENINGS": 0,
    "STRENGTH_GAMES": 0,
    "SCIENTIFIC_DECISION": False,
    "SCAN_READS": 0,
}
POSITIVE_L2 = {1e-6, 1e-5, 1e-4}


def full_sha(value, size):
    return isinstance(value, str) and len(value) == size and all(
        character in "0123456789abcdef" for character in value
    )


def build_facts(source):
    if source.get("schema") != "jass.jfi.boundary_b_input.v1":
        raise ValueError("unexpected Boundary-B input schema")
    if source.get("markers") != ZERO_MARKERS:
        raise ValueError("Boundary-B zero-marker drift")
    if not full_sha(source.get("code_sha"), 40):
        raise ValueError("Boundary-B code SHA drift")
    machine = source.get("machine", {})
    if not (
        machine.get("host") == "cpx62" and int(machine.get("nproc", 0)) == 16
        and machine.get("avx2") is True and machine.get("bmi2") is True
        and machine.get("native_build") is True
    ):
        raise ValueError("Boundary-B CPX62 native machine drift")
    disk = source.get("disk", {})
    if int(disk.get("scratch_free_bytes", 0)) <= 20 * 1024**3:
        raise ValueError("Boundary-B requires more than 20 GiB scratch free")
    ab = source.get("jfi_a_b", {})
    selected_l2 = float(ab.get("selected_l2", 0.0))
    if (
        ab.get("path_verdict") != "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED"
        or selected_l2 not in POSITIVE_L2 or not full_sha(ab.get("code_sha"), 40)
        or ab.get("full_fits") != 7
    ):
        raise ValueError("JFI-A/B prerequisite drift")
    ident = ab.get("identifiability", {})
    if (
        float(ident.get("selected_l2", 0.0)) != selected_l2
        or int(ident.get("coordinates", 0)) <= 0
        or float(ident.get("effective_df", -1.0)) < 0
        or not isinstance(ident.get("class_counts"), dict)
    ):
        raise ValueError("JFI-B identifiability summary drift")
    source40 = source.get("source_40m", {})
    if (
        source40.get("records") != 40_000_000
        or source40.get("external_teacher_inputs") != 0
        or not full_sha(source40.get("data_sha256"), 64)
        or not full_sha(source40.get("meta_sha256"), 64)
    ):
        raise ValueError("authenticated Jass-only 40M source drift")
    candidate = source.get("candidate_universe", {})
    if (
        candidate.get("records") != 10_000_000
        or int(candidate.get("train_candidates", 0)) <= 4_000_000
        or int(candidate.get("train_candidates", 0)) + int(candidate.get("dev_eval", 0)) != 10_000_000
        or candidate.get("target_reads") != 0 or candidate.get("scan_reads") != 0
        or not full_sha(candidate.get("manifest_sha256"), 64)
    ):
        raise ValueError("frozen candidate-universe contract drift")
    sizer = source.get("selector_sizer", {})
    if (
        not 0 < int(sizer.get("rows", 0)) <= 20_000
        or float(sizer.get("seconds", 0.0)) <= 0
        or float(sizer.get("rows_per_second", 0.0)) <= 0
        or int(sizer.get("full_train_candidates", 0)) != candidate["train_candidates"]
        or (sizer.get("guards") or {}).get("TARGET_READS") != 0
        or (sizer.get("guards") or {}).get("ARM_SELECTIONS") != 0
    ):
        raise ValueError("bounded selector sizer drift")
    fit = source.get("fit_projection", {})
    if float(fit.get("two_arm_seconds", 0.0)) <= 0 or int(fit.get("per_arm_timeout_seconds", 0)) <= 0:
        raise ValueError("JFI-C fit ETA/timeout facts required")
    return {
        "schema": "jass.jfi.boundary_b_facts.v1",
        "verdict": "JFI_BOUNDARY_B_READY",
        "code_sha": source["code_sha"],
        "machine": machine, "numeric_env": source.get("numeric_env"), "disk": disk,
        "jfi_a_b": ab, "source_40m": source40, "candidate_universe": candidate,
        "selector_sizer": sizer, "fit_projection": fit,
        "markers": dict(ZERO_MARKERS),
        "next_boundary": "GO JFI ACTIVE",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    facts = build_facts(json.loads(Path(args.input).read_text()))
    Path(args.out).write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n")
    print("JFI_BOUNDARY_B_READY TARGET_READS_BEFORE_SELECTION_FREEZE=0 SCAN_READS=0")
    print("NEXT_BOUNDARY = GO JFI ACTIVE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
