#!/usr/bin/env python3
"""ED4-FRESH W pre-target sizing: structural JSM2 counts only, no outcome read."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

SEED = 202609120402
RECORD_TARGET = 4096
JNNW_REC = 38
JSM2_REC = 25
CURRICULUM = (
    "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
    "20260814T191555Z-18c38a33",
    "18c38a33ae78c9c2e8e2df62fca266da28dacead",
)
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
CURRICULUM_PATH = "artefacts/D-c-prior-then-current.pjtw.gz"
PHASES = [
    "authenticate-frozen-generator",
    "build-engine",
    "generate-sizing-metadata",
    "sanitize-and-summarize",
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _dist(values: list[int]) -> dict[str, float | int]:
    if not values:
        raise ValueError("empty_group_distribution")
    ordered = sorted(values)
    def q(frac: float) -> int:
        return ordered[round((len(ordered) - 1) * frac)]
    return {
        "min": ordered[0],
        "p10": q(0.10),
        "p25": q(0.25),
        "median": float(statistics.median(ordered)),
        "p75": q(0.75),
        "p90": q(0.90),
        "max": ordered[-1],
        "mean": float(statistics.fmean(ordered)),
    }


def sanitize_jnnw(source: Path, dest: Path) -> int:
    """Blindly zero the WDL byte; never branch on or decode its previous value."""
    raw = bytearray(source.read_bytes())
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("jnnw_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * JNNW_REC:
        raise ValueError("jnnw_size")
    for i in range(count):
        raw[8 + i * JNNW_REC + 37] = 0
    dest.write_bytes(raw)
    return count


def sanitize_and_summarize_jsm2(source: Path, dest: Path) -> dict:
    """Read structural fields only. JSM2 game_result (offset 23) is never decoded."""
    raw = bytearray(source.read_bytes())
    if len(raw) < 8 or raw[:4] != b"JSM2":
        raise ValueError("jsm2_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * JSM2_REC:
        raise ValueError("jsm2_size")
    games: dict[int, int] = {}
    openings: dict[int, int] = {}
    game_to_opening: dict[int, int] = {}
    for i in range(count):
        off = 8 + i * JSM2_REC
        game_id = struct.unpack_from("<Q", raw, off)[0]
        opening_id = struct.unpack_from("<Q", raw, off + 8)[0]
        seeded = raw[off + 16]
        ply = struct.unpack_from("<H", raw, off + 17)[0]
        game_plies = struct.unpack_from("<H", raw, off + 19)[0]
        _last_eps_ply = struct.unpack_from("<H", raw, off + 21)[0]
        # off+23 is game_result. Deliberately do not read it.
        flags = raw[off + 24]
        if seeded not in (0, 1) or not ply < game_plies:
            raise ValueError("jsm2_structure")
        if flags & 0xFC:  # no TB relabel and no reserved bits in this frozen recipe
            raise ValueError("jsm2_flags")
        if game_id in game_to_opening and game_to_opening[game_id] != opening_id:
            raise ValueError("game_opening_drift")
        game_to_opening[game_id] = opening_id
        games[game_id] = games.get(game_id, 0) + 1
        openings[opening_id] = openings.get(opening_id, 0) + 1
        raw[off + 23] = 0
    dest.write_bytes(raw)
    return {
        "records": count,
        "independent_games": len(games),
        "independent_openings": len(openings),
        "records_per_game": _dist(list(games.values())),
        "records_per_opening": _dist(list(openings.values())),
        "game_result_parsed": False,
    }


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(artifact, mode)
    job = os.environ.get("JASS_JOB_ID", "unknown")
    attempt = os.environ.get("JASS_ATTEMPT_ID", "unknown")
    raw_root = Path("/var/tmp") / f"jass-ed4-w-sizing-{job}-{attempt}"
    raw_jnnw = raw_root / "raw.jnnw"
    raw_jsm2 = raw_root / "raw.jsm2"
    try:
        if mode != "rehearsal":
            raise ValueError("sizing_rehearsal_only")
        if raw_root.exists() or raw_root.is_symlink():
            raise ValueError("raw_scratch_exists")
        raw_root.mkdir(mode=0o700)
        work = result / "work"
        inputs = result / "inputs"
        work.mkdir(parents=True, exist_ok=True)
        inputs.mkdir(parents=True, exist_ok=True)

        ev.begin(PHASES[0])
        source_job, source_attempt, source_code = CURRICULUM
        verified = fetch_files(
            rclone="rclone",
            prefix=f"r2:jass-data/runs/{source_job}/{source_attempt}",
            selections=[(CURRICULUM_PATH, "curriculum.pjtw.gz")],
            out_dir=inputs,
            expected_state="completed",
        )
        identity = (
            verified.get("job_id"), verified.get("attempt_id"), verified.get("code_sha"),
            verified.get("result_state"), verified.get("exit_code"),
        )
        if identity != (source_job, source_attempt, source_code, "completed", 0):
            raise ValueError("curriculum_source_identity")
        with gzip.open(inputs / "curriculum.pjtw.gz", "rb") as src, (work / "curriculum.pjtw").open("xb") as dst:
            shutil.copyfileobj(src, dst)
        if sha(work / "curriculum.pjtw") != CURRICULUM_SHA:
            raise ValueError("curriculum_model_hash")
        ev.complete()

        ev.begin(PHASES[1])
        archive = work / "repo.tar"
        with archive.open("xb") as stream:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=stream, check=True, timeout=60)
        src_root = work / "src"
        src_root.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(src_root)], check=True, timeout=60)
        subprocess.run(
            [sys.executable, "pattern_jass/tools/gen_patterns.py", "--emit", "--variant", "8cf"],
            cwd=src_root, check=True, timeout=120,
        )
        build = work / "build"
        subprocess.run([
            "cmake", "-S", str(src_root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
            "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON",
            "-DJASS_SCAN_PARITY=ON", "-DJASS_TEMPO_STAGE=ON",
        ], check=True, timeout=180)
        subprocess.run(["cmake", "--build", str(build), "-j16", "--target", "jass"], check=True, timeout=600)
        binary = build / "jass"
        if not binary.is_file():
            raise ValueError("jass_binary_missing")
        ev.complete()

        ev.begin(PHASES[2])
        gen_log = work / "w-sizing-generator.log"
        command = [
            str(binary), "--gen-data-wdl", str(RECORD_TARGET), str(raw_jnnw),
            "4", "8", "260", str(SEED),
            "--nnue", str(work / "curriculum.pjtw"),
            "--wdl-zero-score", "--random-open-plies", "8",
            "--split-selfplay-rngs", "--pair-openings", "--drop-plycap",
            "--sample-meta-out", str(raw_jsm2), "--sample-meta-format", "jsm2",
        ]
        with gen_log.open("xb") as stream:
            subprocess.run(command, cwd=src_root, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=900)
        if not raw_jnnw.is_file() or not raw_jsm2.is_file():
            raise ValueError("generator_outputs_missing")
        ev.complete()

        ev.begin(PHASES[3])
        safe_jnnw = artifact / "w-sizing-scorefree.jnnw"
        safe_jsm2 = artifact / "w-sizing-meta-zeroed.jsm2"
        jnnw_count = sanitize_jnnw(raw_jnnw, safe_jnnw)
        structural = sanitize_and_summarize_jsm2(raw_jsm2, safe_jsm2)
        if jnnw_count != RECORD_TARGET or structural["records"] != RECORD_TARGET:
            raise ValueError("sizing_record_count")
        if structural["independent_games"] < 32 or structural["independent_openings"] < 16:
            raise ValueError("sizing_group_support")
        ev.value["actual_side_effects"]["selfplay_games"] = structural["independent_games"]
        ev.save()
        report = {
            "schema": "jass.ed4.fresh_w_sizing.v1",
            "state": "completed",
            "terminal": "ED4_FRESH_W_SIZING_COMPLETE_V1",
            "classification": "PRE_TARGET_STRUCTURAL_SIZING_ONLY",
            "master_seed": SEED,
            "record_target": RECORD_TARGET,
            **structural,
            "recipe": {
                "eval_depth": 4, "play_depth": 8, "max_plies": 260,
                "random_open_plies": 8, "epsilon_exploration": 0,
                "pair_openings": True, "split_selfplay_rngs": True,
                "drop_plycap": True, "adjudication": False, "tb_relabel": False,
                "sample_meta_format": "jsm2", "wdl_zero_score": True,
                "pattern_geometry": "8cf",
            },
            "curriculum_source": {
                "job_id": source_job, "attempt_id": source_attempt,
                "code_sha": source_code, "model_sha256": CURRICULUM_SHA,
            },
            "sanitized": {
                "jnnw_sha256": sha(safe_jnnw),
                "jsm2_sha256": sha(safe_jsm2),
                "jnnw_wdl_zeroed_before_publication": True,
                "jsm2_game_result_zeroed_before_publication": True,
                "raw_wdl_parsed": False,
                "raw_game_result_parsed": False,
            },
            "candidate_reads": 0,
            "control_evaluations": 0,
            "test_target_reads": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "production_group_count_frozen": False,
            "next_stage": "FREEZE_W_PRODUCTION_GROUP_COUNT_FROM_SIZING_V1",
        }
        atomic_json(artifact / "ed4-fresh-w-sizing.json", report)
        atomic_json(artifact / "scientific-summary.json", report)
        ev.complete()
        ev.finish()
        return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(artifact / "scientific-summary.json", {
            "schema": "jass.ed4.fresh_w_sizing_failure.v1",
            "state": "failed",
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "test_target_reads": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
        })
        return 2
    finally:
        shutil.rmtree(raw_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
