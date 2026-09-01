#!/usr/bin/env python3
"""Validate same-machine JFI Boundary-C force preflight facts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ZERO_MARKERS = {
    "FRESH_OPENINGS": 0,
    "STRENGTH_GAMES": 0,
    "SCIENTIFIC_DECISION": False,
    "SCAN_READS": 0,
    "PROMOTION_AUTHORIZED": False,
}


def digest(value, size):
    return isinstance(value, str) and len(value) == size and all(c in "0123456789abcdef" for c in value)


def build_facts(source):
    if source.get("schema") != "jass.jfi.boundary_c_input.v1":
        raise ValueError("unexpected Boundary-C input schema")
    if source.get("markers") != ZERO_MARKERS:
        raise ValueError("Boundary-C zero-marker drift")
    machine = source.get("machine", {})
    if not (machine.get("host") == "cpx62" and machine.get("nproc") == 16
            and machine.get("avx2") is True and machine.get("bmi2") is True):
        raise ValueError("Boundary-C CPX62 ISA drift")
    disk = source.get("disk", {})
    if int(disk.get("scratch_free_bytes", 0)) <= 20 * 1024**3:
        raise ValueError("Boundary-C requires >20 GiB scratch free")
    candidate = source.get("candidate", {})
    curriculum = source.get("curriculum", {})
    executable = source.get("executable", {})
    if candidate.get("name") != "JASS_NATIVE_ACTIVE_V1" or not digest(candidate.get("sha256"), 64):
        raise ValueError("Boundary-C candidate identity drift")
    if curriculum.get("sha256") != "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1":
        raise ValueError("Boundary-C CURRICULUM SHA drift")
    if not digest(executable.get("sha256"), 64) or executable.get("same_binary_both_arms") is not True:
        raise ValueError("Boundary-C executable contract drift")
    rates = source.get("consumed_root_sizers", {})
    projections = {}
    for view in ("native_0p1s", "q00_depth9"):
        item = rates.get(view, {})
        games = int(item.get("games", 0)); seconds = float(item.get("seconds", 0.0))
        if not 0 < games <= 32 or seconds <= 0 or item.get("candidate_vs_itself") is not True:
            raise ValueError(f"Boundary-C {view} sizer drift")
        projections[view] = {
            **item,
            "games_per_second": games / seconds,
            "projected_pool1_seconds_6000_games": seconds * 6000 / games,
        }
    runtime = source.get("force_runtime", {})
    if (
        runtime.get("shards") != 12 or runtime.get("parallelism") != 12
        or int(runtime.get("per_game_timeout_seconds", 0)) <= 0
        or int(runtime.get("per_view_timeout_seconds", 0)) <= 0
    ):
        raise ValueError("Boundary-C force timeout/parallelism drift")
    return {
        "schema": "jass.jfi.boundary_c_facts.v1",
        "verdict": "JFI_BOUNDARY_C_READY",
        "code_sha": source.get("code_sha"), "machine": machine, "disk": disk,
        "candidate": candidate, "curriculum": curriculum, "executable": executable,
        "consumed_root_sizers": projections, "force_runtime": runtime,
        "markers": dict(ZERO_MARKERS), "next_boundary": "GO JFI FORCE",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True); ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    facts = build_facts(json.loads(Path(args.input).read_text()))
    Path(args.out).write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n")
    print("JFI_BOUNDARY_C_READY FRESH_OPENINGS=0 STRENGTH_GAMES=0 PROMOTION_AUTHORIZED=FALSE")
    print("NEXT_BOUNDARY = GO JFI FORCE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
