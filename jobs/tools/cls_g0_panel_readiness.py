#!/usr/bin/env python3
"""Frozen, study-local CLS panel player and opening contracts.

The stage owns admission, source authentication and publication.  This module
only supplies deterministic opening selection and fresh-player match plumbing;
it never schedules work or reads historical strength helpers.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import os
import signal
import time
from collections import Counter
from pathlib import Path
from statistics import fmean

NATIVE_SOURCE_ANCHOR = "7b789a0c675ce08868fe4a8fcef0becaa4193286"
AUDIT_2072_ATTEMPT = "20260921T053109Z-20a09597"
AUDIT_2072_CODE = "20a09597c6ccdf48829e16287e6ae3efd78d3805"
AUDIT_2072_JOB = "cpx62-2072-l3-cls-g0-panel-historical-audit-publication-retry-v3"
AUDIT_2072_LAUNCH_RECEIPT = "c490e576800d91d239e191effe52c4bfe4dae3e47d4c4ec1eb7b488af1b0857f"
AUDIT_2072_TERMINAL = "CLS_G0_PANEL_HISTORICAL_RAW_AUDIT_COMPLETE_V1"
AUDIT_2072_VERDICT = "FULL_PIPELINE_REHEARSAL_PASS"
MODELS = {
    "CURRICULUM": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
    "LOCAL": "197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450",
    "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6",
}
POOL_SIZE, POOL_SEED, ORDER_SEED = 2048, 2026092011, 2026092012
MAIN_COUNT, REPRESENTATIVE_COUNT = 288, 8
DETERMINISTIC_COUNT, TIMED_COUNT, TOTAL_GAMES = 8, 48, 56
WORKERS, MAX_PLIES, NOMINAL_MS, RESPONSE_MS = 4, 160, 100, 120
GAME_TIMEOUT, PAIR_TIMEOUT, STAGE_TIMEOUT, DISPATCHER_TIMEOUT = 60, 180, 1800, 2400
MAX_SEARCHES = 9072
WARM_FEN = "W:W31-50:B1-20"


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def model_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _fen_state(fen: str) -> tuple:
    need(isinstance(fen, str) and "\n" not in fen and "\r" not in fen, "FEN_TEXT")
    parts = fen.split(":")
    need(len(parts) == 3 and parts[0] in ("W", "B"), "FEN_SHAPE")
    occupied, groups = set(), [set(), set(), set(), set()]
    for part, colour, base in ((parts[1], "W", 0), (parts[2], "B", 2)):
        need(part.startswith(colour), "FEN_COLOUR")
        for token in ([] if not part[1:] else part[1:].split(",")):
            king = token.startswith("K")
            numbers = token[1 if king else 0:].split("-")
            need(len(numbers) in (1, 2) and all(x.isdigit() for x in numbers), "FEN_TOKEN")
            low, high = int(numbers[0]), int(numbers[-1])
            need(1 <= low <= high <= 50, "FEN_RANGE")
            for square in range(low, high + 1):
                need(square not in occupied, "FEN_OVERLAP")
                occupied.add(square); groups[base + int(king)].add(square)
    return (parts[0], *(tuple(sorted(x)) for x in groups))


def canonical_identity(fen: str) -> str:
    state = _fen_state(fen)
    boards = [sum(1 << (square - 1) for square in state[i]) for i in range(1, 5)]
    def fmt(values, stm):
        return ":".join(f"{value:013x}" for value in values) + f":{stm}"
    rotated = [sum(1 << (50 - square) for square in state[i]) for i in (3, 4, 1, 2)]
    return min(fmt(boards, int(state[0] == "B")), fmt(rotated, int(state[0] == "W")))


def require_authenticated_audit_2072(receipt: dict) -> None:
    """Fail closed unless the published historical audit is the exact admission."""
    # ``receipt`` must be the fresh, authenticated R2 readback envelope, not a
    # locally reconstructed summary. The stage MUST authenticate it with
    # ``fetch_result_files`` before calling this parser.
    readback = receipt.get("readback", receipt)
    record = receipt.get("record")
    summary = readback.get("summary", {})
    need(readback.get("job_id") == AUDIT_2072_JOB, "AUDIT_2072_JOB")
    need(readback.get("attempt_id") == AUDIT_2072_ATTEMPT, "AUDIT_2072_ATTEMPT")
    need(readback.get("code_sha") == AUDIT_2072_CODE, "AUDIT_2072_CODE")
    need(summary.get("terminal") == AUDIT_2072_TERMINAL, "AUDIT_2072_TERMINAL")
    need(readback.get("verdict") == AUDIT_2072_VERDICT, "AUDIT_2072_VERDICT")
    need(readback.get("launch_receipt_sha256") == AUDIT_2072_LAUNCH_RECEIPT, "AUDIT_2072_LAUNCH_RECEIPT")
    if record is not None:
        need(all(record.get(key) == readback.get(key) for key in ("job_id", "attempt_id", "code_sha")), "AUDIT_2072_RECORD_IDENTITY")
        need(record.get("terminal") == summary.get("terminal") and record.get("publication_verdict") == readback.get("verdict"), "AUDIT_2072_RECORD_VERDICT")
        need(record.get("launch_receipt_sha256") == readback.get("launch_receipt_sha256"), "AUDIT_2072_RECORD_RECEIPT")
    need(readback.get("new_match_admitted") is False, "AUDIT_2072_MATCH_ADMISSION")
    need(summary.get("historical_2069_raw_audit_passed") is True, "AUDIT_2072_RAW_AUDIT")
    need(summary.get("native_continuity_passed") is True, "AUDIT_2072_NATIVE_CONTINUITY")
    need(summary.get("frozen_g0_verdicts") == {"HIER": "FAIL", "LOCAL": "FAIL", "WDL": "FAIL"}, "AUDIT_2072_G0")
    need(readback.get("completed_phases") == ["authenticate-archives", "verify-native-continuity", "replay-2069", "audit-all-g0-roots", "publish-audit"], "AUDIT_2072_PHASES")
    raw = readback.get("raw_audit", {})
    need(raw.get("passed") is True and raw.get("historical_requests_verified") == 62005 and raw.get("native_terminal_legality_checks") == 576, "AUDIT_2072_COVERAGE")
    publication = readback.get("publication", {})
    need(publication.get("state") == "verified" and publication.get("result_state") == "completed", "AUDIT_2072_PUBLICATION")
    need(tuple(publication.get(key) for key in ("job_id", "attempt_id", "code_sha", "host", "exit_code")) ==
         (AUDIT_2072_JOB, AUDIT_2072_ATTEMPT, AUDIT_2072_CODE, "cpx62", 0), "AUDIT_2072_PUBLICATION_IDENTITY")
    files = {row.get("local_name"): row.get("sha256") for row in publication.get("files", [])}
    need(files.get("launch-receipt.json") == AUDIT_2072_LAUNCH_RECEIPT and
         files.get("historical-2069-raw-audit.json") == "dd5fd56e6782fc89459fbff936d127029b602fa648ab494d7ca50cc819c9f389", "AUDIT_2072_HASHES")


def _parse_native_pool(raw: bytes) -> list[str]:
    """Parse the native ``--gen-opening-pool`` format after byte identity binds it."""
    try:
        lines = [line.split(b"#", 1)[0].strip().decode("utf-8") for line in raw.splitlines()]
    except UnicodeDecodeError as exc:
        raise ValueError("POOL_UTF8") from exc
    return [line for line in lines if line]


def seal_openings(pool_a_raw: bytes, pool_b_raw: bytes, forbidden: set[str]) -> dict:
    """Replay the exact native pool and seal a score-blind canonical selection."""
    # Compare exact generator bytes before parsing; line reconstruction could
    # otherwise hide newline, encoding, or trailing-byte drift.
    need(isinstance(pool_a_raw, bytes) and isinstance(pool_b_raw, bytes) and pool_a_raw == pool_b_raw, "POOL_REPLAY_MISMATCH")
    pool_a = _parse_native_pool(pool_a_raw)
    need(len(pool_a) == POOL_SIZE, "POOL_CARDINALITY")
    rows = {}
    for fen in pool_a:
        identity = canonical_identity(fen)
        rows.setdefault(identity, fen)
    allowed = [(identity, fen) for identity, fen in rows.items() if identity not in forbidden]
    need(len(allowed) >= MAIN_COUNT + REPRESENTATIVE_COUNT, "INSUFFICIENT_ADMISSIBLE_OPENINGS")
    allowed.sort(key=lambda x: (digest([ORDER_SEED, x[0]]), x[0]))
    selected = [{"canonical": identity, "fen": fen} for identity, fen in allowed[:MAIN_COUNT + REPRESENTATIVE_COUNT]]
    seal = {
        "pool_size": POOL_SIZE, "pool_seed": POOL_SEED, "order_seed": ORDER_SEED,
        "pool_sha256": hashlib.sha256(pool_a_raw).hexdigest(),
        "canonicalization": "tb_frontier_symmetry_dedup_rotate180_colour_swap_board_stm",
        "selection_key": "sha256_canonical_json([2026092012,canonical_fingerprint])",
        "forbidden_sha256": digest(sorted(forbidden)), "main": selected[:MAIN_COUNT],
        "representative": selected[MAIN_COUNT:],
    }
    seal["selection_sha256"] = digest(seal)
    validate_seal(seal, forbidden)
    return seal


def validate_seal(seal: dict, forbidden: set[str]) -> None:
    expected = digest({k: v for k, v in seal.items() if k != "selection_sha256"})
    need(seal.get("selection_sha256") == expected, "OPENING_SEAL_HASH")
    need(seal.get("pool_size") == POOL_SIZE and seal.get("pool_seed") == POOL_SEED and seal.get("order_seed") == ORDER_SEED and
         isinstance(seal.get("pool_sha256"), str) and len(seal["pool_sha256"]) == 64, "OPENING_SEEDS")
    need(seal.get("canonicalization") == "tb_frontier_symmetry_dedup_rotate180_colour_swap_board_stm" and
         seal.get("selection_key") == "sha256_canonical_json([2026092012,canonical_fingerprint])" and
         seal.get("forbidden_sha256") == digest(sorted(forbidden)), "OPENING_SELECTION_CONTRACT")
    rows = seal.get("main", []) + seal.get("representative", [])
    need(len(seal.get("main", [])) == MAIN_COUNT and len(seal.get("representative", [])) == REPRESENTATIVE_COUNT, "OPENING_COUNTS")
    need(len({row.get("canonical") for row in rows}) == MAIN_COUNT + REPRESENTATIVE_COUNT, "OPENING_DUPLICATES")
    need(all(canonical_identity(row.get("fen")) == row.get("canonical") and row.get("canonical") not in forbidden for row in rows), "OPENING_IDENTITY_OR_EXCLUSION")
    ordered = sorted(rows, key=lambda row: (digest([ORDER_SEED, row["canonical"]]), row["canonical"]))
    need(rows == ordered, "OPENING_ORDER")


def make_readiness_tasks(work: Path, exe: Path, seal: dict, forbidden: set[str]) -> list[dict]:
    """The sole 56-game apparatus plan; no comparative or production task exists."""
    validate_seal(seal, forbidden)
    tasks = []
    for index, row in enumerate(seal["representative"][:4]):
        tasks.append(_task(work, exe, f"deterministic-{index:02d}-CURRICULUM", row["fen"], "CURRICULUM", "deterministic"))
    for arm in ("CURRICULUM", "LOCAL", "WDL"):
        for index, row in enumerate(seal["representative"]):
            tasks.append(_task(work, exe, f"timed-{arm}-{index:02d}", row["fen"], arm, "timed"))
    need(len(tasks) == 28 and len({task["task_id"] for task in tasks}) == 28, "READINESS_PAIR_PLAN")
    return tasks


def _task(work: Path, exe: Path, task_id: str, opening: str, arm: str, kind: str) -> dict:
    need(arm in MODELS and kind in ("deterministic", "timed"), "READINESS_TASK_SCOPE")
    return {"task_id": task_id, "mode": "rehearsal", "kind": kind, "opening": opening,
            "arm_a": arm, "arm_b": arm, "exe": str(exe),
            "model_a": str(work / f"{arm}.pjtw"), "model_b": str(work / f"{arm}.pjtw"),
            "counts": str(work / f"{task_id}.counts.json"), "output": str(work / f"{task_id}.json")}


def validate_explicit_models(task: dict) -> None:
    need(task.get("arm_a") in MODELS and task.get("arm_b") in MODELS, "EXPLICIT_MODEL_ARMS")
    for role in ("a", "b"):
        path = Path(task[f"model_{role}"])
        need(path.is_file() and not path.is_symlink(), "MODEL_REGULAR_INPUT")
        need(model_sha(path) == MODELS[task[f"arm_{role}"]], "MODEL_SHA:" + role)


def _native_pair(task: dict, a_white: bool, counts: dict, persist_counts) -> dict:
    """Run one fresh, explicitly loaded readiness game.

    Process construction is inside the measured wall clock.  Each player gets
    exactly one depth-one warmup at startpos and is then reset by ``play_game``.
    This deliberately has no arm inference or dependence on historical helpers.
    """
    need(task.get("mode") in ("rehearsal", "production") and task.get("kind") in ("deterministic", "timed") and
         task.get("arm_a") in MODELS and task.get("arm_b") in MODELS, "PANEL_WORKER_SCOPE")
    validate_explicit_models(task)
    from jobs.tools.calibrate_vs_scan import JassEngine, Referee, play_game
    requests, warmups, opened = [], [], []
    started = time.monotonic()
    class Observed(JassEngine):
        warming = True
        def _read_until(self, predicate, timeout_s=60.0):
            lines = super()._read_until(predicate, timeout_s=timeout_s)
            need(bool(lines) and not lines[-1].startswith("error"), "ENGINE_PROTOCOL")
            return lines
        def go_verbose(self, depth=None, movetime=None):
            counts["new_jass_searches"] += 1; persist_counts()
            begin = time.monotonic()
            move, lines = super().go_verbose(depth=depth, movetime=movetime)
            fields = {key: int(value) for key, value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", lines[-1])}
            need({"nodes", "depth", "evalcalls"} <= fields.keys(), "NATIVE_TELEMETRY")
            value = {"side": self.label, "nodes": fields["nodes"], "depth": fields["depth"],
                     "eval_calls": fields["evalcalls"], "wall_seconds": time.monotonic() - begin,
                     "move": None if move is None else move.jass_apply_str()}
            if self.warming:
                value["requested_depth"] = 1
            elif task["kind"] == "timed":
                value["requested_movetime_ms"] = NOMINAL_MS
            else:
                value["requested_depth"] = 3
            (warmups if self.warming else requests).append(value)
            if not self.warming and task["kind"] == "timed":
                need(value["wall_seconds"] <= RESPONSE_MS / 1000, "RESPONSE_CEILING")
            return move, lines
    class StrictReferee(Referee):
        def apply_move(self, move):
            need(super().apply_move(move), "ILLEGAL_MOVE")
            return True
    previous_alarm = None
    if os.name != "nt":
        def expired(signum, frame): raise TimeoutError("GAME_HARD_TIMEOUT")
        previous_alarm = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, GAME_TIMEOUT)
    try:
        counts["strength_games"] += 1; persist_counts()
        for label, role in (("A", "a"), ("B", "b")):
            engine = Observed(task["exe"], label=label, pattern_path=task["model_" + role],
                              enforce_no_book=True, search_params=None, threads=1)
            opened.append(engine)
            engine.new_game(); engine.set_position_fen(WARM_FEN); engine.go(depth=1); engine.warming = False
        referee = StrictReferee(task["exe"]); opened.append(referee)
        result = play_game(opened[0] if a_white else opened[1], opened[1] if a_white else opened[0], referee,
                           task["opening"], depth=3 if task["kind"] == "deterministic" else None,
                           movetime=None if task["kind"] == "deterministic" else NOMINAL_MS / 1000,
                           max_plies=MAX_PLIES, game_timeout_s=GAME_TIMEOUT)
        if result.reason == "ply cap" and not referee.has_legal_moves():
            result.outcome = "L" if result.fens[-1].startswith("W") else "W"
            result.reason = "no legal move from cap-terminal"
        score = .5 if result.outcome == "D" else float((result.outcome == "W") == a_white)
        row = {"opening": task["opening"], "a_is_white": a_white, "outcome": result.outcome,
               "score_a": score, "reason": result.reason, "plies": result.plies, "fens": result.fens,
               "moves": result.moves, "warmup_requests": warmups, "requests": requests,
               "game_wall_seconds": time.monotonic() - started}
        validate_game(row, task)
        validate_explicit_models(task)
        return row
    finally:
        for engine in reversed(opened):
            engine.close()
        if previous_alarm is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_alarm)


def native_self_pair(task: dict, a_white: bool, counts: dict, persist_counts) -> dict:
    """Readiness-only spelling: it may never execute a cross-arm pair."""
    need(task.get("arm_a") == task.get("arm_b") in MODELS, "READINESS_SELF_PAIR_ONLY")
    return _native_pair(task, a_white, counts, persist_counts)


def run_self_pair(task: dict, counts: dict, persist_counts) -> dict:
    """Run both colours and record a wall time spanning all game startups."""
    started = time.monotonic()
    games = [native_self_pair(task, colour, counts, persist_counts) for colour in (True, False)]
    row = {key: task[key] for key in ("task_id", "opening", "arm_a", "arm_b", "kind")}
    row.update(games=games, pair_wall_seconds=time.monotonic() - started)
    need(row["pair_wall_seconds"] <= PAIR_TIMEOUT, "PAIR_TIMEOUT")
    validate_explicit_models(task)
    return row


def run_pair(task: dict, counts: dict, persist_counts) -> dict:
    """Run a colour-swapped pair with two explicitly pinned model files.

    ``run_self_pair`` remains the readiness spelling; production callers use
    this name so a cross-arm comparison cannot be accidentally represented as
    a readiness self-pair.
    """
    started = time.monotonic()
    games = [_native_pair(task, colour, counts, persist_counts) for colour in (True, False)]
    row = {key: task[key] for key in ("task_id", "opening", "arm_a", "arm_b", "kind")}
    row.update(games=games, pair_wall_seconds=time.monotonic() - started)
    need(row["pair_wall_seconds"] <= PAIR_TIMEOUT, "PAIR_TIMEOUT")
    validate_explicit_models(task)
    return row


def validate_game(game: dict, task: dict) -> None:
    need(game.get("opening") == task["opening"], "GAME_OPENING")
    need(type(game.get("a_is_white")) is bool and game.get("outcome") in ("W", "D", "L"), "GAME_OUTCOME")
    need(game.get("reason") not in ("game time cap",) and not str(game.get("reason")).startswith("illegal move"), "TECHNICAL_GAME")
    need(game.get("reason") in ("25-move rule", "3-fold repetition", "ply cap") or str(game.get("reason")).startswith("no legal move from "), "GAME_REASON")
    need(type(game.get("plies")) is int and 0 < game["plies"] <= MAX_PLIES, "GAME_PLIES")
    need(len(game.get("fens", [])) == len(game.get("moves", [])) + 1 == game["plies"] + 1, "GAME_TRAJECTORY")
    need(game["fens"][0] == task["opening"], "GAME_START")
    expected = .5 if game["outcome"] == "D" else float((game["outcome"] == "W") == game["a_is_white"])
    need(game.get("score_a") == expected, "GAME_SCORE")
    warm, requests = game.get("warmup_requests"), game.get("requests")
    need(isinstance(warm, list) and len(warm) == 2 and [q.get("side") for q in warm] == ["A", "B"], "WARMUP_COVERAGE")
    need(isinstance(requests, list) and 0 < len(requests) <= MAX_PLIES, "GAME_REQUESTS")
    for request in warm:
        need(request.get("requested_depth") == 1, "WARMUP_DEPTH")
    for request in requests:
        wall = request.get("wall_seconds")
        need(type(wall) in (float, int) and math.isfinite(wall) and wall > 0, "REQUEST_WALL")
        if task["kind"] == "timed":
            need(wall <= RESPONSE_MS / 1000 and request.get("requested_movetime_ms") == NOMINAL_MS and "requested_depth" not in request, "NOMINAL_CADENCE")
        else:
            need(request.get("requested_depth") == 3 and "requested_movetime_ms" not in request, "DETERMINISTIC_DEPTH")


def validate_readiness_rows(rows: list[dict], tasks: list[dict], *, timed_block_wall_seconds: float) -> dict:
    need(len(rows) == len(tasks) == 28, "READINESS_PAIR_COVERAGE")
    walls, trajectories = [], set()
    by_id = {row.get("task_id"): row for row in rows}
    need(len(by_id) == len(rows) and set(by_id) == {task["task_id"] for task in tasks}, "READINESS_TASK_IDENTITIES")
    for task in tasks:
        row = by_id[task["task_id"]]
        need(all(row.get(k) == task[k] for k in ("task_id", "opening", "arm_a", "arm_b", "kind")), "READINESS_PAIR_IDENTITY")
        games = row.get("games")
        need(isinstance(games, list) and len(games) == 2 and [g.get("a_is_white") for g in games] == [True, False], "READINESS_COLOURS")
        for game in games:
            validate_game(game, task)
            trajectories.update(canonical_identity(fen) for fen in game["fens"])
        pair_wall = row.get("pair_wall_seconds")
        need(type(pair_wall) in (float, int) and math.isfinite(pair_wall) and pair_wall > 0, "PAIR_WALL_STARTUP_INCLUSIVE")
        walls.append((task, float(pair_wall)))
        if task["kind"] == "deterministic":
            need(sum(game["score_a"] for game in games) == 1, "DETERMINISTIC_SELF_SCORE")
            need(games[0]["fens"] == games[1]["fens"], "DETERMINISTIC_TRAJECTORY")
    timed = [(task, wall) for task, wall in walls if task["kind"] == "timed"]
    need(len(timed) == 24 and sum(1 for task, _ in walls if task["kind"] == "deterministic") == 4, "READINESS_BLOCKS")
    need(type(timed_block_wall_seconds) in (float, int) and math.isfinite(timed_block_wall_seconds) and timed_block_wall_seconds > 0, "TIMED_BLOCK_WALL")
    timed_block_wall = float(timed_block_wall_seconds)
    factor = max(1.0, 4 * timed_block_wall / sum(wall for _, wall in timed))
    means = {arm: fmean(wall for task, wall in timed if task["arm_a"] == arm) for arm in MODELS}
    projection = {arm: factor * max(means[arm], means["CURRICULUM"]) * MAIN_COUNT / WORKERS for arm in ("LOCAL", "WDL")}
    need(all(value <= 3000 for value in projection.values()), "READINESS_RESOURCE_PROJECTION")
    return {"pairs": 28, "games": TOTAL_GAMES, "timed_pairs": 24, "deterministic_pairs": 4,
            "timed_block_wall_seconds": timed_block_wall, "pair_wall_startup_inclusive": True,
            "parallelism_factor": factor, "mean_pair_wall_seconds": means,
            "projected_main_work_seconds": projection, "trajectory_canonicals": trajectories}


def validate_freshness(seal: dict, readiness: dict) -> None:
    main = {row["canonical"] for row in seal["main"]}
    representative = {row["canonical"] for row in seal["representative"]}
    need(not main & readiness["trajectory_canonicals"], "MAIN_START_IN_READINESS_TRAJECTORY")
    need(not representative & main, "SEALED_MAIN_REPRESENTATIVE_OVERLAP")


def validate_effect_counts(counts: dict) -> None:
    games, searches = counts.get("strength_games"), counts.get("new_jass_searches")
    need(type(games) is int and 0 <= games <= TOTAL_GAMES, "READINESS_GAME_BUDGET")
    need(type(searches) is int and 0 <= searches <= MAX_SEARCHES, "READINESS_SEARCH_BUDGET")
    need(all(counts.get(key, 0) == 0 for key in ("fits", "new_scan_searches", "selfplay_games", "promotions", "bakes", "test_target_reads")), "READINESS_FORBIDDEN_EFFECT")
