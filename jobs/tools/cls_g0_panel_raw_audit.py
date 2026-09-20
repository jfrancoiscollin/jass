#!/usr/bin/env python3
"""Independent read-only checks for the frozen CLS rejection panel.

No fitting, evaluation, engine search, new games, historical analyzer imports,
or G0 redecision. Native replay is injected only as a legality oracle.
"""
from __future__ import annotations

from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
from typing import Callable

RAW_LIMIT = 64 * 1024**2
EXPANDED_LIMIT = 128 * 1024**2
MAX_PLIES = 160
PAIRS = 288
G0_FAIL = "CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1"
MODELS = {
    "CURRICULUM": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
    "LOCAL": "197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450",
    "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6",
    "HIER": "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628",
}


class AuditError(ValueError):
    """An audit discrepancy, not a new scientific verdict."""


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise AuditError(reason)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024**2), b""):
            h.update(b)
    return h.hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256((raw + "\n").encode()).hexdigest()


def _object(pairs: list[tuple]) -> dict:
    out = {}
    for k, v in pairs:
        need(k not in out, "DUPLICATE_JSON_KEY:" + k)
        out[k] = v
    return out


def decode(raw: bytes) -> dict:
    def reject(value):
        raise AuditError("NONFINITE_JSON:" + value)
    value = json.loads(raw, object_pairs_hook=_object, parse_constant=reject)
    need(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def read(path: Path, *, expanded_limit: int = EXPANDED_LIMIT) -> dict:
    need(path.is_file() and not path.is_symlink(), "REGULAR_INPUT_REQUIRED")
    need(0 < path.stat().st_size <= RAW_LIMIT, "RAW_SIZE_BOUND")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            raw = f.read(expanded_limit + 1)
        need(len(raw) <= expanded_limit, "GZIP_EXPANSION_BOUND")
    else:
        raw = path.read_bytes()
    return decode(raw)


def unpack_model(source: Path, target: Path, expected_sha: str) -> dict:
    need(source.is_file() and not source.is_symlink(), "MODEL_REGULAR_INPUT")
    need(0 < source.stat().st_size <= RAW_LIMIT, "MODEL_RAW_BOUND")
    need(not target.exists() and not target.is_symlink(), "MODEL_NO_CLOBBER")
    total = 0
    with gzip.open(source, "rb") as f, target.open("xb") as g:
        for b in iter(lambda: f.read(1024**2), b""):
            total += len(b)
            need(total <= EXPANDED_LIMIT, "MODEL_EXPANSION_BOUND")
            g.write(b)
    need(total > 0 and sha(target) == expected_sha, "MODEL_SHA_MISMATCH")
    target.chmod(0o444)
    return {"raw_sha256": expected_sha, "raw_bytes": total, "gzip_sha256": sha(source)}


def fen_state(fen: str) -> tuple:
    need(isinstance(fen, str) and "\n" not in fen and "\r" not in fen, "FEN_TEXT")
    parts = fen.split(":")
    need(len(parts) == 3 and parts[0] in ("W", "B"), "FEN_SHAPE")
    occupied, pieces = set(), [set(), set(), set(), set()]
    for part, colour, offset in ((parts[1], "W", 0), (parts[2], "B", 2)):
        need(part.startswith(colour), "FEN_COLOUR")
        tokens = part[1:].split(",") if part[1:] else []
        for token in tokens:
            m = re.fullmatch(r"(K?)([0-9]+)(?:-([0-9]+))?", token)
            need(m is not None, "FEN_TOKEN")
            low, high = int(m[2]), int(m[3] or m[2])
            need(1 <= low <= high <= 50, "FEN_RANGE")
            for square in range(low, high + 1):
                need(square not in occupied, "FEN_OVERLAP")
                occupied.add(square)
                pieces[offset + bool(m[1])].add(square)
    return (parts[0], *(tuple(sorted(x)) for x in pieces))


def canonical_identity(fen: str) -> str:
    state = fen_state(fen)
    boards = [sum(1 << (s - 1) for s in xs) for xs in state[1:]]
    stm = int(state[0] == "B")
    def fmt(b, s):
        return ":".join(f"{v:013x}" for v in b) + f":{s}"
    rotated = [sum(1 << (50 - s) for s in state[i]) for i in (3, 4, 1, 2)]
    return min(fmt(boards, stm), fmt(rotated, 1 - stm))


def exact_move(text: str) -> tuple[int, int, tuple[int, ...]]:
    need(isinstance(text, str), "MOVE_TEXT")
    m = re.fullmatch(r"([0-9]+)([-x])([0-9]+)(?: captures=([0-9]+(?:,[0-9]+)*))?", text)
    need(m is not None, "EXACT_MOVE_SYNTAX")
    origin, dest = int(m[1]), int(m[3])
    captures = tuple(int(s) for s in m[4].split(",")) if m[4] else ()
    need(1 <= origin <= 50 and 1 <= dest <= 50, "MOVE_SQUARE")
    need(all(1 <= s <= 50 for s in captures) and len(set(captures)) == len(captures), "CAPTURE_SET")
    need((m[2] == "x") == bool(captures), "CAPTURE_IDENTITY_REQUIRED")
    return origin, dest, tuple(sorted(captures))


def check_telemetry(q: dict, *, warmup: bool = False) -> None:
    need(isinstance(q, dict) and q.get("side") in ("A", "B"), "REQUEST_SIDE")
    for name in ("nodes", "depth", "eval_calls"):
        need(type(q.get(name)) is int and q[name] >= 0, "REQUEST_INTEGER:" + name)
    wall = q.get("wall_seconds")
    need(type(wall) in (float, int) and math.isfinite(wall) and wall > 0, "REQUEST_WALL")
    need(warmup or wall <= .120, "CADENCE_OVER_120MS")


def inspect_game(game: dict) -> dict:
    """Validate raw correspondence; leave legal move generation to native replay."""
    need(type(game.get("a_is_white")) is bool, "COLOUR_BOOL")
    n = game.get("plies")
    need(type(n) is int and 0 < n <= MAX_PLIES, "PLY_COUNT")
    fens, moves, requests = game["fens"], game["moves"], game["requests"]
    need(len(fens) == n + 1 and len(moves) == n, "TRAJECTORY_CARDINALITY")
    need(game["opening"] == fens[0], "TRAJECTORY_START")
    states = [fen_state(f) for f in fens]
    need(len(requests) in (n, n + 1) and len(requests) <= MAX_PLIES, "REQUEST_COUNT")
    warm = game.get("warmup_requests", [])
    need(len(warm) == 2 and [q.get("side") for q in warm] == ["A", "B"], "WARMUP_COVERAGE")
    for q in warm:
        check_telemetry(q, warmup=True)
        exact_move(q["move"])
    for i, q in enumerate(requests):
        check_telemetry(q)
        stm = states[min(i, n)][0]
        expected_side = "A" if ((stm == "W") == game["a_is_white"]) else "B"
        need(q["side"] == expected_side, "REQUEST_COLOUR_ORDER")
    if len(requests) == n + 1:
        need(requests[-1].get("move") in (None, "0-0"), "EXTRA_REQUEST_NOT_TERMINAL")
    clock, repetitions = 0, Counter([states[0]])
    exact = []
    for i, q in enumerate(requests[:n]):
        frm, to, caps = exact_move(q["move"])
        need(moves[i] == q["move"].split(" ", 1)[0], "LOGGED_MOVE_CAPTURE_MISMATCH")
        before, after = states[i], states[i + 1]
        need(before[0] != after[0], "SIDE_TO_MOVE_NOT_FLIPPED")
        own_men = before[1] if before[0] == "W" else before[3]
        own_kings = before[2] if before[0] == "W" else before[4]
        need(frm in own_men or frm in own_kings, "MOVE_ORIGIN_NOT_OWN")
        clock = 0 if caps or frm in own_men else clock + 1
        repetitions[after] += 1
        need(i == n - 1 or (clock < 50 and repetitions[after] < 3), "PLAY_CONTINUED_AFTER_DRAW")
        exact.append(q["move"])
    need(game["outcome"] in ("W", "D", "L") and game["score_a"] in (0, .5, 1), "OUTCOME_SCORE")
    expected_score = .5 if game["outcome"] == "D" else float((game["outcome"] == "W") == game["a_is_white"])
    need(game["score_a"] == expected_score, "COLOUR_SCORING")
    need(type(game.get("game_wall_seconds")) in (int, float) and
         math.isfinite(game["game_wall_seconds"]) and game["game_wall_seconds"] > 0, "GAME_WALL")
    return {"exact_moves": exact, "final_state": states[-1], "clock": clock,
            "repetitions": repetitions[states[-1]], "searches": len(requests) + len(warm),
            "extra_null": len(requests) == n + 1}


def check_terminal(game: dict, meta: dict, legal_moves: int) -> None:
    need(type(legal_moves) is int and legal_moves >= 0, "LEGAL_COUNT")
    reason = game["reason"]
    if legal_moves == 0:
        expected = "L" if meta["final_state"][0] == "W" else "W"
        side = "A" if ((meta["final_state"][0] == "W") == game["a_is_white"]) else "B"
        need(game["outcome"] == expected, "TERMINAL_WIN_LOSS")
        need(reason in ("no legal move from " + side, "no legal move from cap-terminal"), "TERMINAL_REASON")
        need(reason != "no legal move from cap-terminal" or game["plies"] == MAX_PLIES, "CAP_TERMINAL_PLY")
    else:
        need(not meta["extra_null"] and game["outcome"] == "D", "NONTERMINAL_RESULT")
        expected_reason = ("25-move rule" if meta["clock"] >= 50 else
                           "3-fold repetition" if meta["repetitions"] >= 3 else "ply cap")
        need(reason == expected_reason, "DRAW_REASON")
        need(reason != "ply cap" or game["plies"] == MAX_PLIES, "EARLY_PLY_CAP")


def validate_opening_seal(seal: dict, expected_sha: str) -> None:
    need(seal.get("selection_sha256") == expected_sha, "OPENING_SELECTION_IDENTITY")
    need(digest({k: v for k, v in seal.items() if k != "selection_sha256"}) == expected_sha, "OPENING_SEAL_HASH")
    need(len(seal["main"]) == PAIRS and len(seal["representative"]) == 8, "OPENING_SEAL_COUNTS")
    rows = seal["main"] + seal["representative"]
    need(len({r["canonical"] for r in rows}) == 296, "OPENING_SEAL_DUPLICATES")
    need(all(canonical_identity(r["fen"]) == r["canonical"] for r in rows), "OPENING_CANONICAL_IDENTITY")


def independent_interval(pair_bounds: list[tuple[float, float]], alpha: float) -> dict:
    need(len(pair_bounds) == PAIRS, "COMPLETE_288_PAIRS_REQUIRED")
    need(all(0 <= low <= high <= 1 for low, high in pair_bounds), "PAIR_BOUNDS")
    low = statistics.fmean(x[0] for x in pair_bounds)
    high = statistics.fmean(x[1] for x in pair_bounds)
    radius = math.sqrt(math.log(2 / alpha) / (2 * PAIRS))
    ci = [max(0.0, low - radius), min(1.0, high + radius)]
    boundary = 1 / (1 + 10**.25)
    verdict = ("SUBSTANTIAL_LOSS_SUPPORTED" if ci[1] < boundary else
               "SUBSTANTIAL_LOSS_EXCLUDED" if ci[0] > boundary else "INDETERMINATE")
    return {"score_interval": ci, "censored_pair_mean_bounds": [low, high],
            "hoeffding_radius": radius, "score_boundary": boundary,
            "statistical_verdict": verdict}


def audit_match(raw: dict, seal: dict, summary: dict,
                replay: Callable[[list[dict], list[dict]], list[int]],
                progress: Callable[[dict], None] = lambda _: None) -> dict:
    need(raw.get("mode") == "production", "HISTORICAL_MODE")
    pairs = raw.get("pairs")
    need(isinstance(pairs, list) and len(pairs) == PAIRS, "HISTORICAL_PAIR_COUNT")
    need(summary.get("models") == {k: MODELS[k] for k in ("CURRICULUM", "HIER")}, "HISTORICAL_MODELS")
    validate_opening_seal(seal, summary["opening_selection_sha256"])
    flat, metas, bounds, scores = [], [], [], []
    for i, pair in enumerate(pairs):
        need(pair.get("task_id") == f"pair-{i:04d}-HIER", "PAIR_ORDER_IDENTITY")
        need((pair.get("arm_a"), pair.get("arm_b")) == ("HIER", "CURRICULUM"), "PAIR_MODELS")
        need(pair.get("opening") == seal["main"][i]["fen"], "PAIR_OPENING")
        games = pair.get("games")
        need(isinstance(games, list) and len(games) == 2 and
             [g.get("a_is_white") for g in games] == [True, False], "PAIR_COLOURS")
        for g in games:
            need(g.get("opening") == pair["opening"], "GAME_PAIR_OPENING")
            metas.append(inspect_game(g))
            flat.append(g)
        low = sum(0 if g["reason"] == "ply cap" else g["score_a"] for g in games) / 2
        high = sum(1 if g["reason"] == "ply cap" else g["score_a"] for g in games) / 2
        bounds.append((low, high))
        scores.append(sum(g["score_a"] for g in games) / 2)
    progress({"phase": "native-legality-replay", "historical_games_checked": len(flat)})
    counts = replay(flat, metas)
    need(len(counts) == 576, "NATIVE_TERMINAL_COVERAGE")
    for g, meta, count in zip(flat, metas, counts):
        check_terminal(g, meta, count)
    result = independent_interval(bounds, .05)  # Original 2069, NOT new panel alpha.
    result.update(pairs=PAIRS, games=len(flat),
        administratively_censored_games=sum(g["reason"] == "ply cap" for g in flat),
        descriptive_half_point_ply_cap_score=statistics.fmean(scores),
        descriptive_pentanomial_counts=dict(Counter(str(2 * x) for x in scores)))
    for key, value in result.items():
        other = summary.get(key)
        if isinstance(value, list):
            need(isinstance(other, list) and len(value) == len(other) and
                 all(math.isclose(a, b, abs_tol=1e-12, rel_tol=0) for a, b in zip(value, other)), "READOUT_DRIFT:" + key)
        elif type(value) is float:
            need(type(other) in (float, int) and math.isclose(value, other, abs_tol=1e-12, rel_tol=0), "READOUT_DRIFT:" + key)
        else:
            need(other == value, "READOUT_DRIFT:" + key)
    searches = sum(m["searches"] for m in metas)
    need(summary["actual_side_effects"]["new_jass_searches"] == searches, "HISTORICAL_SEARCH_ACCOUNTING")
    need(result["administratively_censored_games"] == 10 and
         result["statistical_verdict"] == "SUBSTANTIAL_LOSS_EXCLUDED", "HISTORICAL_FROZEN_RESULT")
    return {"schema": "jass.cls_panel_2069_raw_audit.v1", "passed": True,
        "basis": "authenticated_raw_576_trajectories_and_native_legality_replay",
        "recomputed_original_readout": result, "historical_requests_verified": searches,
        "native_moves_replayed": sum(g["plies"] for g in flat),
        "native_terminal_legality_checks": len(flat), "new_engine_searches": 0,
        "new_games": 0, "historical_alpha_unchanged": True,
        "per_game_model_claim_basis": "authenticated_runtime_and_worker_source_receipts",
        "maximum_scored_response_seconds": max(q["wall_seconds"] for g in flat for q in g["requests"]),
        "no_new_scientific_verdict": True}


def g0_rows(arm: str, rows: list[dict], roots: list[str], phases: list[dict],
            probe: dict, summary: dict) -> tuple[list[dict], dict]:
    need(arm in ("LOCAL", "WDL"), "PANEL_ARM")
    need(len(roots) == len(set(roots)) == 512 and len(rows) == 1024, "G0_CARDINALITY")
    need(summary.get("candidate_arm") == arm and summary.get("candidate_sha256") == MODELS[arm]
         and summary.get("direct_parent_sha256") == MODELS["CURRICULUM"]
         and summary.get("terminal") == G0_FAIL, "G0_SOURCE_BOUNDARY")
    need([str(p["parent_id"]) for p in phases] == roots, "G0_PHASE_ORDER")
    need(Counter(p["phase"] for p in phases) == {p: 128 for p in ("P0", "P1", "P2", "P3")}, "G0_PHASE_QUOTAS")
    by_key = {(str(r["root_id"]), r["arm"]): r for r in rows}
    need(len(by_key) == 1024 and set(by_key) == {(r, a) for r in roots for a in ("parent", "candidate")}, "G0_ARM_COVERAGE")
    missing = {"parent": [], "candidate": []}
    out = []
    for root, phase in zip(roots, phases):
        parent, candidate = by_key[(root, "parent")], by_key[(root, "candidate")]
        pd, cd = int(parent["completed_nominal_depth"]), int(candidate["completed_nominal_depth"])
        target = max(1, pd - 1)
        for role, r, depth in (("parent", parent, pd), ("candidate", candidate, cd)):
            need(int(r["target_depth"]) == target and depth >= 0, "G0_DEPTH_TARGET")
            nodes, wall, nps = int(r["nodes_observed"]), int(r["wall_us"]), float(r["nps"])
            need(0 < nodes <= 200000 and wall > 0 and math.isfinite(nps) and nps > 0, "G0_NUMERIC")
            need(int(r["trace_attempts"]) > 0 and bool(r["bestmove_canonical"]), "G0_TRACE_OR_MOVE")
            receipt = r["nodes_to_target"]
            if receipt == "":
                missing[role].append(root)
            else:
                need(0 < int(receipt) <= nodes and depth >= target, "G0_RECEIPT_INVALID")
        absent = candidate["nodes_to_target"] == ""
        category = ("profondeur_cible_non_atteinte" if absent and cd < target else
                    "profondeur_atteinte_sans_recu_exact" if absent else "recu_exact_present")
        out.append({"candidate": arm, "root_id": root, "phase": phase["phase"],
            "canonical_fingerprint": phase["canonical_fingerprint"],
            "parent_depth": pd, "candidate_depth": cd, "target_depth": target,
            "depth_delta": cd - pd, "candidate_receipt_missing": int(absent),
            "classification": category, "parent_nodes": parent["nodes_observed"],
            "candidate_nodes": candidate["nodes_observed"], "parent_nodes_to_target": parent["nodes_to_target"],
            "candidate_nodes_to_target": candidate["nodes_to_target"],
            "parent_nps": parent["nps"], "candidate_nps": candidate["nps"],
            "parent_move": parent["bestmove_canonical"], "candidate_move": candidate["bestmove_canonical"],
            "same_move": int(parent["bestmove_canonical"] == candidate["bestmove_canonical"])})
    for role in missing:
        need(probe.get(role + "_nodes_to_depth_missing_roots") == missing[role], "G0_MISSING_INVENTORY")
    need(probe.get("budget_nodes") == 200000 and probe.get("roots") == 512 and
         probe.get("trace_parity_mismatches") == 0 and probe.get("nodes_to_depth_surrogate_used") is False, "G0_PROBE_BOUNDARY")
    need(len(missing["candidate"]) == 56 and not missing["parent"], "G0_HISTORICAL_COUNTS")
    return out, {"arm": arm, "roots": 512, "input_rows": len(rows),
        "categories": dict(Counter(r["classification"] for r in out)),
        "frozen_g0_verdict": "FAIL", "g0_recomputed": False, "imputed_receipts": 0}


def tsv(path: Path) -> list[dict]:
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= RAW_LIMIT, "TSV_BOUND")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    need(bool(rows) and all(None not in r and all(v is not None for v in r.values()) for r in rows), "TSV_SHAPE")
    return rows
