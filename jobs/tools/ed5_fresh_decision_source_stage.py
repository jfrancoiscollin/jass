#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
from jobs.tools import ed4_fresh_decision_source_stage as base

MASTER = 202609140501
RESERVE = 202609140511
FILES = base.FILES


def validate_seed(seed: int) -> None:
    if seed not in (MASTER, RESERVE):
        raise ValueError("seed_not_preregistered")


def main() -> int:
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(art, mode)
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        master = int(os.environ.get("ED5_FRESH_D_MASTER_SEED", str(MASTER)))
        validate_seed(master)

        ev.begin("build-seeded-source")
        work = result / "work"
        src = work / "src"
        build = work / "build"
        source = art / "source"
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
        exclusions = work / "exclusions.txt"
        exclusions.write_text("")
        generator_mode = "production" if mode == "production" else "smoke"
        subprocess.run([str(binary), str(exclusions), str(source), generator_mode, str(master)], check=True, timeout=240)
        ev.complete()

        ev.begin("validate-and-seal")
        validated = base.validate(source, mode, master)
        seal = {
            "schema": "jass.ed5.fresh_d_source_seal.v1",
            "state": "completed",
            "terminal": "ED5_FRESH_D_SOURCE_SEALED_V1",
            "mode": mode,
            "master_seed": master,
            "reserve_seed_used": master == RESERVE,
            "generator_sha256": base.sha(binary),
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "created_at_unix": int(time.time()),
            "files": {name: base.sha(source / name) for name in FILES},
            **validated,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "automatic_target_scoring": False,
            "next_stage": "GENERATE_AND_SEAL_ED5_W_AND_S_SOURCES",
        }
        atomic_json(art / "cohort-seal.json", seal)
        atomic_json(art / "scientific-summary.json", seal)
        ev.complete()
        ev.finish()
        return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art / "scientific-summary.json", {
            "schema": "jass.ed5.fresh_d_source_failure.v1",
            "state": "failed",
            "terminal": "ED5_FRESH_D_SOURCE_TECHNICAL_FAILURE_V1",
            "error_type": type(exc).__name__,
            "target_reads": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
