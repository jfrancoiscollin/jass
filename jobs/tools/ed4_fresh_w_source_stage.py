#!/usr/bin/env python3
"""ED4-FRESH W source: seal 8192 score-free rows before any outcome read."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.fetch_result_files import fetch_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
from jobs.tools import ed4_fresh_w_sizing_stage as sizing

SEED = 202609120402
RESERVE_SEED = 202609120412
JNNW_REC = 38
JSM2_REC = 25
ROWS_PER_GAME = 8
GAMES_PER_OPENING = 2
PRODUCTION_POSITIONS = 8192
PRODUCTION_OPENINGS = 512
PRODUCTION_RECORD_BUDGETS = (40960, 45056, 49152, 53248, 57344)
REHEARSAL_OPENINGS = 32
REHEARSAL_POSITIONS = REHEARSAL_OPENINGS * GAMES_PER_OPENING * ROWS_PER_GAME
REHEARSAL_RECORD_BUDGET = 4096

SIZING = (
    "cpx62-1948-l3-ed4-fresh-w-sizing-rehearsal-v2",
    "20260913T220257Z-7782dc2b",
    "7782dc2b5fa79e02711d5c898cb91ee6bf7b691a",
)
SIZING_PATH = "artefacts/ed4-fresh-w-sizing.json"
CURRICULUM = sizing.CURRICULUM
CURRICULUM_SHA = sizing.CURRICULUM_SHA
CURRICULUM_PATH = sizing.CURRICULUM_PATH
PHASES = [
    "authenticate-sizing-and-model",
    "build-engine",
    "generate-score-free-source",
    "select-and-seal",
]


class SupportInsufficient(RuntimeError):
    def __init__(self, report: dict):
        super().__init__("ed4_fresh_w_source_support_insufficient")
        self.report = report


def ceil_to(value: float, step: int) -> int:
    return int(math.ceil(value / step) * step)


def derive_plan(report: dict) -> dict:
    """Derive the frozen production plan from structural sizing only."""
    required = {
        "schema": "jass.ed4.fresh_w_sizing.v1",
        "terminal": "ED4_FRESH_W_SIZING_COMPLETE_V1",
        "master_seed": SEED,
        "records": 4096,
        "independent_games": 118,
        "independent_openings": 65,
        "game_result_parsed": False,
        "candidate_reads": 0,
        "control_evaluations": 0,
        "test_target_reads": 0,
        "fits": 0,
        "alpha_spent": 0,
        "confirmation_target_consumed": False,
    }
    for key, value in required.items():
        if report.get(key) != value:
            raise ValueError(f"sizing_{key}")
    if report.get("records_per_game", {}).get("min") != 13:
        raise ValueError("sizing_game_min")
    if report.get("records_per_opening", {}).get("median") != 64.0:
        raise ValueError("sizing_opening_median")
    if report.get("records_per_opening", {}).get("p90") != 90:
        raise ValueError("sizing_opening_p90")
    sanitized = report.get("sanitized", {})
    if not (
        sanitized.get("jnnw_wdl_zeroed_before_publication") is True
        and sanitized.get("jsm2_game_result_zeroed_before_publication") is True
        and sanitized.get("raw_wdl_parsed") is False
        and sanitized.get("raw_game_result_parsed") is False
    ):
        raise ValueError("sizing_target_barrier")
    openings = int(report["independent_openings"])
    games = int(report["independent_games"])
    if not openings <= games <= 2 * openings:
        raise ValueError("sizing_pair_shape")
    paired = games - openings
    if paired != 53:
        raise ValueError("sizing_paired_openings")
    quota = 1 << (int(report["records_per_game"]["min"]).bit_length() - 1)
    if quota != ROWS_PER_GAME:
        raise ValueError("sizing_row_quota")
    target_openings = PRODUCTION_POSITIONS // (GAMES_PER_OPENING * quota)
    if target_openings != PRODUCTION_OPENINGS:
        raise ValueError("production_opening_count")
    represented_needed = math.ceil(target_openings * openings / paired)
    initial = ceil_to(represented_needed * float(report["records_per_opening"]["median"]), 4096)
    maximum = ceil_to(represented_needed * int(report["records_per_opening"]["p90"]), 4096)
    if represented_needed != 628 or initial != PRODUCTION_RECORD_BUDGETS[0] or maximum != PRODUCTION_RECORD_BUDGETS[-1]:
        raise ValueError("sizing_mechanical_derivation")
    return {
        "rows_per_game": quota,
        "games_per_opening": GAMES_PER_OPENING,
        "target_positions": PRODUCTION_POSITIONS,
        "target_openings": target_openings,
        "sizing_paired_openings": paired,
        "sizing_represented_openings": openings,
        "estimated_represented_openings_needed": represented_needed,
        "record_budget_initial": initial,
        "record_budget_step": 4096,
        "record_budget_max": maximum,
        "record_budget_ladder": list(PRODUCTION_RECORD_BUDGETS),
        "cluster_unit": "opening_id",
    }


def parse_zero_jsm2(source: Path, dest: Path) -> list[dict]:
    """Parse structural JSM2 fields only and blindly zero game_result byte 23."""
    raw = bytearray(source.read_bytes())
    if len(raw) < 8 or raw[:4] != b"JSM2":
        raise ValueError("jsm2_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * JSM2_REC:
        raise ValueError("jsm2_size")
    rows: list[dict] = []
    game_to_opening: dict[int, int] = {}
    for index in range(count):
        off = 8 + index * JSM2_REC
        game_id = struct.unpack_from("<Q", raw, off)[0]
        opening_id = struct.unpack_from("<Q", raw, off + 8)[0]
        seeded = raw[off + 16]
        ply = struct.unpack_from("<H", raw, off + 17)[0]
        game_plies = struct.unpack_from("<H", raw, off + 19)[0]
        last_eps_ply = struct.unpack_from("<H", raw, off + 21)[0]
        # off+23 is game_result: deliberately never decoded.
        flags = raw[off + 24]
        if seeded not in (0, 1) or not ply < game_plies:
            raise ValueError("jsm2_structure")
        if flags & 0xFC:
            raise ValueError("jsm2_flags")
        if game_id in game_to_opening and game_to_opening[game_id] != opening_id:
            raise ValueError("game_opening_drift")
        game_to_opening[game_id] = opening_id
        rows.append({
            "raw_row_index": index,
            "game_id": game_id,
            "opening_id": opening_id,
            "seeded": seeded,
            "ply": ply,
            "game_plies": game_plies,
            "last_eps_ply": last_eps_ply,
            "flags": flags,
        })
        raw[off + 23] = 0
    dest.write_bytes(raw)
    return rows


def select_rows(rows: list[dict], opening_target: int) -> tuple[list[int], list[dict], dict]:
    openings: dict[int, dict[int, list[dict]]] = {}
    for row in rows:
        games = openings.setdefault(row["opening_id"], {})
        games.setdefault(row["game_id"], []).append(row)
    if any(len(games) > GAMES_PER_OPENING for games in openings.values()):
        raise ValueError("pair_opening_more_than_two_games")
    eligible: list[tuple[int, dict[int, list[dict]]]] = []
    for opening_id, games in openings.items():
        if len(games) == GAMES_PER_OPENING and all(len(group) >= ROWS_PER_GAME for group in games.values()):
            eligible.append((opening_id, games))
    if len(eligible) < opening_target:
        raise SupportInsufficient({
            "represented_openings": len(openings),
            "eligible_paired_openings": len(eligible),
            "required_paired_openings": opening_target,
            "rows": len(rows),
        })
    selected: list[int] = []
    groups: list[dict] = []
    for opening_rank, (opening_id, games) in enumerate(eligible[:opening_target]):
        for game_slot, (game_id, game_rows) in enumerate(games.items()):
            for within_game_rank, row in enumerate(game_rows[:ROWS_PER_GAME]):
                source_row = len(selected)
                selected.append(row["raw_row_index"])
                groups.append({
                    "source_row": source_row,
                    "opening_rank": opening_rank,
                    "opening_id": opening_id,
                    "game_slot": game_slot,
                    "game_id": game_id,
                    "within_game_rank": within_game_rank,
                    **row,
                })
    expected = opening_target * GAMES_PER_OPENING * ROWS_PER_GAME
    if len(selected) != expected or len(groups) != expected:
        raise ValueError("selected_cardinality")
    return selected, groups, {
        "represented_openings": len(openings),
        "eligible_paired_openings": len(eligible),
        "selected_openings": opening_target,
        "selected_games": opening_target * GAMES_PER_OPENING,
        "selected_positions": expected,
    }


def select_binary(source: Path, dest: Path, indices: list[int], *, magic: bytes, rec_size: int) -> None:
    raw = source.read_bytes()
    if len(raw) < 8 or raw[:4] != magic:
        raise ValueError("binary_magic")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * rec_size:
        raise ValueError("binary_size")
    if any(i < 0 or i >= count for i in indices):
        raise ValueError("binary_index")
    out = bytearray(magic + struct.pack("<I", len(indices)))
    for index in indices:
        off = 8 + index * rec_size
        out.extend(raw[off:off + rec_size])
    dest.write_bytes(out)


def rot50(bits: int) -> int:
    out = 0
    for sq in range(50):
        if bits & (1 << sq):
            out |= 1 << (49 - sq)
    return out


def canonical_position(record: bytes) -> str:
    if len(record) != JNNW_REC:
        raise ValueError("record_size")
    wm, wk, bm, bk = struct.unpack_from("<4Q", record, 0)
    stm = record[32]
    if stm not in (0, 1):
        raise ValueError("stm")
    if any(value >> 50 for value in (wm, wk, bm, bk)):
        raise ValueError("board_bits")
    boards = (wm, wk, bm, bk)
    if any(boards[i] & boards[j] for i in range(4) for j in range(i)):
        raise ValueError("board_overlap")
    def fmt(a: int, b: int, c: int, d: int, side: int) -> str:
        return f"{a:013x}:{b:013x}:{c:013x}:{d:013x}:{side}"
    direct = fmt(wm, wk, bm, bk, stm)
    flipped = fmt(rot50(bm), rot50(bk), rot50(wm), rot50(wk), 1 - stm)
    return min(direct, flipped)


def canonical_digest(jnnw: Path) -> tuple[str, int]:
    raw = jnnw.read_bytes()
    count = struct.unpack_from("<I", raw, 4)[0]
    identities = []
    for index in range(count):
        off = 8 + index * JNNW_REC
        identities.append(canonical_position(raw[off:off + JNNW_REC]))
    unique = sorted(set(identities))
    payload = ("\n".join(unique) + "\n").encode()
    return hashlib.sha256(payload).hexdigest(), len(unique)


def write_groups(path: Path, groups: list[dict]) -> None:
    fields = [
        "source_row", "opening_rank", "opening_id", "game_slot", "game_id",
        "within_game_rank", "raw_row_index", "seeded", "ply", "game_plies",
        "last_eps_ply", "flags",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in groups:
            writer.writerow({key: row[key] for key in fields})


def verify_fetch(receipt: dict, identity: tuple[str, str, str]) -> None:
    job, attempt, code = identity
    observed = (
        receipt.get("job_id"), receipt.get("attempt_id"), receipt.get("code_sha"),
        receipt.get("result_state"), receipt.get("exit_code"),
    )
    if observed != (job, attempt, code, "completed", 0):
        raise ValueError("source_identity")


def main() -> int:
    artifact = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    ev = StageEvidence(artifact, mode)
    job = os.environ.get("JASS_JOB_ID", "unknown")
    attempt = os.environ.get("JASS_ATTEMPT_ID", "unknown")
    scratch = Path("/var/tmp") / f"jass-ed4-w-source-{job}-{attempt}"
    try:
        if mode not in ("rehearsal", "production"):
            raise ValueError("launch_mode")
        if scratch.exists() or scratch.is_symlink():
            raise ValueError("scratch_exists")
        scratch.mkdir(mode=0o700)
        inputs = scratch / "inputs"
        work = scratch / "work"
        inputs.mkdir(); work.mkdir()

        ev.begin(PHASES[0])
        sizing_receipt = fetch_files(
            rclone="rclone",
            prefix=f"r2:jass-data/runs/{SIZING[0]}/{SIZING[1]}",
            selections=[(SIZING_PATH, "ed4-fresh-w-sizing.json")],
            out_dir=inputs / "sizing",
            expected_state="completed",
        )
        verify_fetch(sizing_receipt, SIZING)
        sizing_report = json.loads((inputs / "sizing/ed4-fresh-w-sizing.json").read_text())
        plan = derive_plan(sizing_report)

        curriculum_receipt = fetch_files(
            rclone="rclone",
            prefix=f"r2:jass-data/runs/{CURRICULUM[0]}/{CURRICULUM[1]}",
            selections=[(CURRICULUM_PATH, "curriculum.pjtw.gz")],
            out_dir=inputs / "curriculum",
            expected_state="completed",
        )
        verify_fetch(curriculum_receipt, CURRICULUM)
        with gzip.open(inputs / "curriculum/curriculum.pjtw.gz", "rb") as src, (work / "curriculum.pjtw").open("xb") as dst:
            shutil.copyfileobj(src, dst)
        if sizing.sha(work / "curriculum.pjtw") != CURRICULUM_SHA:
            raise ValueError("curriculum_model_hash")
        ev.complete()

        ev.begin(PHASES[1])
        archive = work / "repo.tar"
        with archive.open("xb") as stream:
            subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=stream, check=True, timeout=60)
        src_root = work / "src"
        src_root.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(src_root)], check=True, timeout=60)
        subprocess.run([sys.executable, "pattern_jass/tools/gen_patterns.py", "--emit", "--variant", "8cf"], cwd=src_root, check=True, timeout=120)
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

        opening_target = REHEARSAL_OPENINGS if mode == "rehearsal" else PRODUCTION_OPENINGS
        expected_positions = REHEARSAL_POSITIONS if mode == "rehearsal" else PRODUCTION_POSITIONS
        default_budget = REHEARSAL_RECORD_BUDGET if mode == "rehearsal" else PRODUCTION_RECORD_BUDGETS[0]
        record_budget = int(os.environ.get("ED4_FRESH_W_RECORD_BUDGET", str(default_budget)))
        allowed = {REHEARSAL_RECORD_BUDGET} if mode == "rehearsal" else set(PRODUCTION_RECORD_BUDGETS)
        if record_budget not in allowed:
            raise ValueError("record_budget_not_preregistered")

        ev.begin(PHASES[2])
        raw_jnnw = scratch / "raw.jnnw"
        raw_jsm2 = scratch / "raw.jsm2"
        gen_log = scratch / "generator.log"
        command = [
            str(binary), "--gen-data-wdl", str(record_budget), str(raw_jnnw),
            "4", "8", "260", str(SEED),
            "--nnue", str(work / "curriculum.pjtw"),
            "--wdl-zero-score", "--random-open-plies", "8",
            "--split-selfplay-rngs", "--pair-openings", "--drop-plycap",
            "--sample-meta-out", str(raw_jsm2), "--sample-meta-format", "jsm2",
        ]
        with gen_log.open("xb") as stream:
            subprocess.run(command, cwd=src_root, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=2100 if mode == "production" else 900)
        if not raw_jnnw.is_file() or not raw_jsm2.is_file():
            raise ValueError("generator_outputs_missing")
        ev.complete()

        ev.begin(PHASES[3])
        safe_jnnw = scratch / "safe-full.jnnw"
        safe_jsm2 = scratch / "safe-full.jsm2"
        jnnw_count = sizing.sanitize_jnnw(raw_jnnw, safe_jnnw)
        rows = parse_zero_jsm2(raw_jsm2, safe_jsm2)
        if jnnw_count != record_budget or len(rows) != record_budget:
            raise ValueError("raw_alignment")
        try:
            selected, groups, support = select_rows(rows, opening_target)
        except SupportInsufficient as exc:
            ladder = list(PRODUCTION_RECORD_BUDGETS)
            next_budget = None
            if mode == "production" and record_budget in ladder:
                pos = ladder.index(record_budget)
                next_budget = ladder[pos + 1] if pos + 1 < len(ladder) else None
            report = {
                "schema": "jass.ed4.fresh_w_source_support.v1",
                "state": "insufficient",
                "terminal": "ED4_FRESH_W_SOURCE_COMPLETION_REQUIRED_V1" if next_budget else "ED4_FRESH_W_SOURCE_INSUFFICIENT_V1",
                "mode": mode,
                "record_budget": record_budget,
                "next_record_budget": next_budget,
                "master_seed": SEED,
                "reserve_seed_used": False,
                **exc.report,
                "target_reads": 0,
                "candidate_reads": 0,
                "control_evaluations": 0,
                "fits": 0,
                "alpha_spent": 0,
                "confirmation_target_consumed": False,
            }
            atomic_json(artifact / "support-report.json", report)
            atomic_json(artifact / "scientific-summary.json", report)
            ev.value["actual_side_effects"]["selfplay_games"] = len({row["game_id"] for row in rows})
            ev.save()
            raise

        source = artifact / "source"
        source.mkdir()
        positions = source / "positions.jnnw"
        meta = source / "meta.jsm2"
        group_path = source / "groups.tsv"
        select_binary(safe_jnnw, positions, selected, magic=b"JNNW", rec_size=JNNW_REC)
        select_binary(safe_jsm2, meta, selected, magic=b"JSM2", rec_size=JSM2_REC)
        write_groups(group_path, groups)
        selected_raw = positions.read_bytes()
        count = struct.unpack_from("<I", selected_raw, 4)[0]
        if count != expected_positions:
            raise ValueError("sealed_position_count")
        for index in range(count):
            rec = selected_raw[8 + index * JNNW_REC:8 + (index + 1) * JNNW_REC]
            if rec[33:38] != b"\0" * 5:
                raise ValueError("target_bytes_not_zero")
        meta_raw = meta.read_bytes()
        if any(meta_raw[8 + i * JSM2_REC + 23] != 0 for i in range(expected_positions)):
            raise ValueError("game_result_not_zero")
        digest, unique_count = canonical_digest(positions)
        opening_ids = {row["opening_id"] for row in groups}
        game_ids = {row["game_id"] for row in groups}
        if len(opening_ids) != opening_target or len(game_ids) != opening_target * 2:
            raise ValueError("sealed_group_count")
        if any(sum(1 for row in groups if row["game_id"] == game_id) != ROWS_PER_GAME for game_id in game_ids):
            raise ValueError("sealed_rows_per_game")

        source_meta = {
            "schema": "jass.ed4.fresh_w_source.v1",
            "mode": mode,
            "master_seed": SEED,
            "reserve_seed": RESERVE_SEED,
            "reserve_seed_used": False,
            "record_budget": record_budget,
            "production_plan": plan,
            "selection": {
                "opening_order": "first_appearance",
                "game_order": "first_appearance_within_opening",
                "row_order": "emission_order",
                "rows_per_game": ROWS_PER_GAME,
                "games_per_opening": GAMES_PER_OPENING,
                "opening_groups": opening_target,
                "positions": expected_positions,
                "cluster_unit": "opening_id",
            },
            "support": support,
            "recipe": sizing_report["recipe"],
            "sizing_source": {"job_id": SIZING[0], "attempt_id": SIZING[1], "code_sha": SIZING[2]},
            "curriculum_source": {"job_id": CURRICULUM[0], "attempt_id": CURRICULUM[1], "code_sha": CURRICULUM[2], "model_sha256": CURRICULUM_SHA},
            "raw_wdl_parsed": False,
            "raw_game_result_parsed": False,
            "jnnw_wdl_zeroed_before_selection": True,
            "jsm2_game_result_zeroed_before_selection": True,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "fits": 0,
            "alpha_spent": 0,
        }
        atomic_json(source / "source.json", source_meta)
        files = {name: sizing.sha(source / name) for name in ("positions.jnnw", "meta.jsm2", "groups.tsv", "source.json")}
        terminal = "ED4_FRESH_W_SOURCE_SEALED_V1" if mode == "production" else "ED4_FRESH_W_SOURCE_REHEARSAL_SEALED_V1"
        seal = {
            "schema": "jass.ed4.fresh_w_source_seal.v1",
            "state": "completed",
            "terminal": terminal,
            "mode": mode,
            "master_seed": SEED,
            "reserve_seed_used": False,
            "record_budget": record_budget,
            "positions": expected_positions,
            "opening_groups": opening_target,
            "game_groups": opening_target * GAMES_PER_OPENING,
            "rows_per_game": ROWS_PER_GAME,
            "cluster_unit": "opening_id",
            "canonical_identity_digest": digest,
            "unique_canonical_identities": unique_count,
            "files": files,
            "raw_wdl_parsed": False,
            "raw_game_result_parsed": False,
            "target_bytes_zeroed": True,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "created_at_unix": int(time.time()),
            "next_stage": "AUTHENTICATE_D_W_S_DISJOINTNESS_BEFORE_TARGET_READ" if mode == "production" else "RUN_AUTHENTICATED_W_SOURCE_PRODUCTION",
        }
        atomic_json(artifact / "cohort-seal.json", seal)
        atomic_json(artifact / "scientific-summary.json", seal)
        ev.value["actual_side_effects"]["selfplay_games"] = len({row["game_id"] for row in rows})
        ev.save()
        ev.complete(); ev.finish(); return 0
    except SupportInsufficient:
        ev.fail(SupportInsufficient({}))
        return 2
    except Exception as exc:
        ev.fail(exc)
        if not (artifact / "scientific-summary.json").exists():
            atomic_json(artifact / "scientific-summary.json", {
                "schema": "jass.ed4.fresh_w_source_failure.v1",
                "state": "failed",
                "terminal": "ED4_FRESH_W_SOURCE_TECHNICAL_FAILURE_V1",
                "error_type": type(exc).__name__,
                "target_reads": 0,
                "candidate_reads": 0,
                "control_evaluations": 0,
                "fits": 0,
                "alpha_spent": 0,
                "confirmation_target_consumed": False,
            })
        return 2
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
