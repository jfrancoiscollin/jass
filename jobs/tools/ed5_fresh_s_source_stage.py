#!/usr/bin/env python3
"""ED5 fresh S score-free roots with explicit pre-target primary/reserve collision test."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_decision_source_stage as base
from jobs.tools import ed5_fresh_w_source_stage as wutil
from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PRIMARY = 202609140503
RESERVE = 202609140513
FILES = base.FILES


def w_identity_from_env() -> tuple[str, str, str]:
    values = tuple(os.environ.get(key, "").strip() for key in (
        "ED5_FRESH_W_JOB", "ED5_FRESH_W_ATTEMPT", "ED5_FRESH_W_CODE_SHA"))
    if not all(values) or len(values[2]) != 40:
        raise ValueError("w_identity_env")
    return values  # type: ignore[return-value]


def fetch_w(result: Path, identity: tuple[str, str, str]) -> set[str]:
    root = result / "ed5-s-w-source"
    receipt = fetch_files(
        rclone="rclone",
        prefix=f"r2:jass-data/runs/{identity[0]}/{identity[1]}",
        selections=[
            ("artefacts/cohort-seal.json", "cohort-seal.json"),
            ("artefacts/source/positions.jnnw", "source/positions.jnnw"),
        ],
        out_dir=root,
        expected_state="completed",
    )
    observed = (receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"), receipt.get("result_state"), receipt.get("exit_code"))
    if observed != (identity[0], identity[1], identity[2], "completed", 0):
        raise ValueError("w_result_identity")
    seal = json.loads((root / "cohort-seal.json").read_text())
    required = {
        "schema": "jass.ed5.fresh_w_source_seal.v1",
        "terminal": "ED5_FRESH_W_SOURCE_SEALED_V1",
        "state": "completed",
        "mode": "production",
        "positions": 8192,
        "opening_groups": 512,
        "game_groups": 1024,
        "rows_per_game": 8,
        "cluster_unit": "opening_id",
        "target_reads": 0,
        "scan_searches": 0,
        "jass_searches": 0,
        "fits": 0,
        "alpha_spent": 0,
        "confirmation_target_consumed": False,
    }
    for key, value in required.items():
        if seal.get(key) != value:
            raise ValueError(f"w_seal_{key}")
    positions = root / "source/positions.jnnw"
    if wutil.sha(positions) != seal["files"]["positions.jnnw"]:
        raise ValueError("w_positions_hash")
    values = wutil.canonical_set(positions)
    if len(values) != int(seal["unique_canonical_identities"]) or wutil.digest(values) != seal["canonical_identity_digest"]:
        raise ValueError("w_canonical_identity")
    return values


def source_ids(source: Path) -> set[str]:
    return wutil.canonical_set(source / "parents.jnnw") | wutil.canonical_set(source / "children.jnnw")


def generate(binary: Path, work: Path, seed: int, mode: str) -> Path:
    source = work / f"source-{seed}"
    generator_mode = "production" if mode == "production" else "smoke"
    exclusions = work / f"exclusions-{seed}.txt"
    exclusions.write_text("")
    subprocess.run([str(binary), str(exclusions), str(source), generator_mode, str(seed)], check=True, timeout=240)
    base.validate(source, mode, seed)
    return source


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(art, mode)
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")

        ev.begin("build-seeded-source")
        d_ids = wutil.fetch_d(result)
        w_identity = w_identity_from_env()
        w_ids = fetch_w(result, w_identity)
        work = result / "work"
        src = work / "src"
        build = work / "build"
        work.mkdir(parents=True, exist_ok=True)
        with (work / "repo.tar").open("wb") as stream:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=stream, check=True)
        src.mkdir()
        subprocess.run(["tar", "-xf", str(work / "repo.tar"), "-C", str(src)], check=True)
        with (src / "CMakeLists.txt").open("a") as handle:
            handle.write("\nadd_executable(jass_ed5_fresh_source jobs/tools/ed4_fresh_source.cpp)\n")
            handle.write("target_link_libraries(jass_ed5_fresh_source PRIVATE jass_lib)\n")
        subprocess.run([
            "cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
            "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
            "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
        ], check=True, timeout=180)
        subprocess.run(["cmake", "--build", str(build), "-j2", "--target", "jass_ed5_fresh_source"], check=True, timeout=180)
        binary = build / "jass_ed5_fresh_source"
        ev.complete()

        ev.begin("generate-score-free-source")
        primary_source = generate(binary, work, PRIMARY, mode)
        primary_ids = source_ids(primary_source)
        d_overlap = primary_ids & d_ids
        w_overlap = primary_ids & w_ids
        reserve_used = bool(d_overlap or w_overlap)
        if reserve_used:
            selected_source = generate(binary, work, RESERVE, mode)
            selected_ids = source_ids(selected_source)
            reserve_d_overlap = selected_ids & d_ids
            reserve_w_overlap = selected_ids & w_ids
            if reserve_d_overlap or reserve_w_overlap:
                raise ValueError("s_reserve_canonical_collision")
            seed = RESERVE
        else:
            selected_source = primary_source
            selected_ids = primary_ids
            seed = PRIMARY
        shutil.copytree(selected_source, art / "source")
        ev.complete()

        ev.begin("validate-and-seal")
        validated = base.validate(art / "source", mode, seed)
        seal = {
            "schema": "jass.ed5.fresh_s_source_seal.v1",
            "state": "completed",
            "terminal": "ED5_FRESH_S_SOURCE_SEALED_V1",
            "mode": mode,
            "parent_preregistered_seed": PRIMARY,
            "master_seed": seed,
            "reserve_seed": RESERVE,
            "reserve_seed_used": reserve_used,
            "reserve_reason": "PRIMARY_S_CANONICAL_COLLISION_PRE_TARGET" if reserve_used else None,
            "primary_collision": {
                "D": {"count": len(d_overlap), "digest": wutil.digest(d_overlap)},
                "W": {"count": len(w_overlap), "digest": wutil.digest(w_overlap)},
            },
            "generator_sha256": base.sha(binary),
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "created_at_unix": int(time.time()),
            "files": {name: base.sha(art / "source" / name) for name in FILES},
            **validated,
            "confirmation_roots": 512 if mode == "production" else 16,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "automatic_target_scoring": False,
            "next_stage": "AUTHENTICATE_ED5_D_W_S_AND_HISTORICAL_DISJOINTNESS",
        }
        atomic_json(art / "cohort-seal.json", seal)
        atomic_json(art / "scientific-summary.json", seal)
        ev.complete()
        ev.finish()
        return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art / "scientific-summary.json", {
            "schema": "jass.ed5.fresh_s_source_failure.v1",
            "state": "failed",
            "terminal": "ED5_FRESH_S_SOURCE_TECHNICAL_FAILURE_V1",
            "error_type": type(exc).__name__,
            "target_reads": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
