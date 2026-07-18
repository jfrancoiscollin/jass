#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gen2-MMTO P3 decision laboratory.

The tool answers two questions without modifying the frozen champion:

1. On P3 positions that Gen2-MMTO fails to convert, does a legal sibling convert?
2. If every child is re-searched with a larger verification budget, does the
   best verified child improve paired conversion on a fresh pool?

It also exports quiet hard-negative pairs for a later through-search MMTO-v2
fit. Engine failures are fatal: a timeout is never converted into a draw.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs" / "tools"))

import calibrate_vs_scan as cv  # type: ignore  # noqa: E402
import conv_fixed_wdl as conv  # type: ignore  # noqa: E402
import conversion_teacher as ct  # type: ignore  # noqa: E402

SCORE_RE = re.compile(r"\bscore=(-?\d+)\b")
DEPTH_RE = re.compile(r"\bdepth=(\d+)\b")
NODES_RE = re.compile(r"\bnodes=(\d+)\b")
VALID_RESULTS = {"win", "draw", "loss"}


@dataclass(frozen=True)
class SearchReply:
    move: cv.Move
    score: int
    depth: int
    nodes: int
    raw: str


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_baseline(paths: Iterable[Path]) -> dict[int, str]:
    merged: dict[int, str] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("n_errors", 0)) != 0:
            raise ValueError(f"{path}: baseline contains engine errors")
        rows = data.get("position_results")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: missing position_results")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{path}: malformed position row")
            result = row.get("result")
            if result not in VALID_RESULTS:
                continue
            index = int(row["index"])
            if index in merged:
                raise ValueError(f"duplicate baseline index {index}")
            merged[index] = str(result)
    if not merged:
        raise ValueError("empty baseline result set")
    return merged


def material_leader(record: bytes) -> tuple[str | None, int, int]:
    wm, wk, bm, bk = struct.unpack_from("<4Q", record, 0)
    white = wm.bit_count() + 3 * wk.bit_count()
    black = bm.bit_count() + 3 * bk.bit_count()
    pieces = sum(bb.bit_count() for bb in (wm, wk, bm, bk))
    if white > black:
        return "W", white - black, pieces
    if black > white:
        return "B", black - white, pieces
    return None, 0, pieces


def p3_leader_winner(record: bytes) -> str | None:
    leader, margin, pieces = material_leader(record)
    winner = conv.winning_side(record)
    return leader if leader is not None and margin == 1 and 8 <= pieces < 20 and winner == leader else None


def search_reply(engine: cv.JassEngine, fen: str, *, depth: int | None,
                 movetime: float | None) -> SearchReply:
    if (depth is None) == (movetime is None):
        raise ValueError("exactly one of depth or movetime is required")
    engine.set_position_fen(fen)
    engine._drain()
    if movetime is not None:
        engine._send(f"go movetime {int(round(movetime * 1000))}")
        timeout_s = movetime * 5.0 + 10.0
    else:
        engine._send(f"go depth {depth}")
        timeout_s = 120.0
    lines = engine._read_until(
        lambda line: line.startswith("bestmove") or line.startswith("error"),
        timeout_s=timeout_s,
    )
    raw = lines[-1]
    if raw.startswith("error"):
        raise RuntimeError(raw)
    move = cv.parse_jass_bestmove(raw)
    score = SCORE_RE.search(raw)
    dep = DEPTH_RE.search(raw)
    nodes = NODES_RE.search(raw)
    if not score or not dep or not nodes:
        raise RuntimeError(f"bestmove line lacks score/depth/nodes: {raw!r}")
    return SearchReply(move, int(score.group(1)), int(dep.group(1)), int(nodes.group(1)), raw)


def child_fen_for_move(referee: cv.Referee, parent_fen: str, move: cv.Move) -> str:
    referee.set_position_fen(parent_fen)
    if not referee.apply_move(move):
        raise RuntimeError(f"engine returned illegal move {move.jass_str()} for {parent_fen}")
    return referee.current_fen()


def board_child(children: list[dict], target_fen: str) -> dict:
    key = ct.board_key(target_fen)
    matches = [row for row in children if ct.board_key(str(row["fen"])) == key]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one child match, found {len(matches)}")
    return matches[0]


def rollout_result(champion: cv.JassEngine, defender: cv.JassEngine,
                   referee: cv.Referee, child_fen: str, leader: str,
                   *, depth: int | None, movetime: float | None,
                   max_plies: int) -> str:
    white, black = (champion, defender) if leader == "W" else (defender, champion)
    kwargs = {"movetime": movetime} if movetime is not None else {"depth": depth}
    game = cv.play_game(white, black, referee, child_fen, max_plies=max_plies, **kwargs)
    champion_won = ((leader == "W" and game.outcome == "W")
                    or (leader == "B" and game.outcome == "L"))
    if game.outcome == "D":
        return "draw"
    return "win" if champion_won else "loss"


def paired_stats(diffs: list[int]) -> dict[str, float | int | None]:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "delta": None, "ci95_low": None, "ci95_high": None}
    mean = sum(diffs) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in diffs) / (n - 1)
        se = math.sqrt(var / n)
    else:
        se = 0.0
    half = 1.96 * se
    return {"n": n, "delta": mean, "ci95_low": mean - half, "ci95_high": mean + half}


def split_name(parent_id: str, holdout_mod: int) -> str:
    bucket = int(hashlib.sha256(parent_id.encode()).hexdigest(), 16) % holdout_mod
    return "holdout" if bucket == 0 else "train"


def normalize_move(move: str) -> tuple[int, int]:
    match = re.match(r"^(\d+)[x-](\d+)$", move)
    if not match:
        raise ValueError(f"unsupported move token {move!r}")
    return int(match.group(1)), int(match.group(2))


def run(args: argparse.Namespace) -> dict[str, object]:
    records = conv.read_records(args.pool_jnnw)
    baseline = load_baseline(args.baseline_json)
    out_dir = Path(args.out_dir)
    work = Path(args.work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    selected: list[tuple[int, bytes, str]] = []
    for index, record in enumerate(records):
        if index % args.nshards != args.shard or index not in baseline:
            continue
        leader = p3_leader_winner(record)
        if leader is None:
            continue
        if args.scope == "failures" and baseline[index] == "win":
            continue
        selected.append((index, record, leader))
        if args.max_parents and len(selected) >= args.max_parents:
            break
    if not selected:
        raise ValueError("no eligible P3 leader-winner positions")

    parent_fens = [conv.record_to_fen(record) for _, record, _ in selected]
    child_rows = ct.dump_children(args.jass, parent_fens, work, "p3-parents")
    if len(child_rows) != len(selected):
        raise RuntimeError("child dump lost parent alignment")

    root = cv.JassEngine(args.jass, label="root", pattern_path=args.pattern,
                         search_params=args.search_params)
    verifier = cv.JassEngine(args.jass, label="verify", pattern_path=args.pattern,
                             search_params=args.search_params)
    champion = cv.JassEngine(args.jass, label="champion", pattern_path=args.pattern,
                             search_params=args.search_params)
    defender = cv.JassEngine(args.defender_jass or args.jass, label="defender",
                             pattern_path=args.defender_pattern,
                             search_params=args.defender_search_params)
    apply_ref = cv.Referee(args.jass)
    game_ref = cv.Referee(args.jass)

    events: list[dict[str, object]] = []
    skipped_capture_parents = 0
    pair_buffers = {
        split: {"parents": [], "good": bytearray(), "bad": bytearray(), "pairs": []}
        for split in ("train", "holdout")
    }
    try:
        for (index, record, leader), children in zip(selected, child_rows):
            if len(children) < 2:
                continue
            # MVP: quiet decisions only. The existing two-byte MMTO move contract
            # cannot disambiguate every international-draughts capture path.
            if any(bool(child.get("capture")) for child in children):
                skipped_capture_parents += 1
                continue
            parent_fen = conv.record_to_fen(record)
            decision = search_reply(root, parent_fen, depth=args.decision_depth,
                                    movetime=args.decision_movetime)
            baseline_child_fen = child_fen_for_move(apply_ref, parent_fen, decision.move)
            baseline_child = board_child(children, baseline_child_fen)

            ranked: list[dict[str, object]] = []
            limited_children = children if args.max_children == 0 else children[:args.max_children]
            for child in limited_children:
                reply = search_reply(verifier, str(child["fen"]),
                                      depth=args.verify_depth,
                                      movetime=args.verify_movetime)
                ranked.append({
                    "move": str(child["move"]),
                    "fen": str(child["fen"]),
                    "capture": bool(child.get("capture")),
                    "verify_child_score": reply.score,
                    "verify_parent_score": -reply.score,
                    "verify_depth": reply.depth,
                    "verify_nodes": reply.nodes,
                })
            if not ranked:
                continue
            ranked.sort(key=lambda row: (-int(row["verify_parent_score"]), str(row["move"])))
            chosen = ranked[:args.top_k]
            bkey = ct.board_key(str(baseline_child["fen"]))
            if all(ct.board_key(str(row["fen"])) != bkey for row in chosen):
                baseline_ranked = next((row for row in ranked if ct.board_key(str(row["fen"])) == bkey), None)
                if baseline_ranked is None:
                    raise RuntimeError("max-children excluded the baseline child")
                chosen.append(baseline_ranked)

            for row in chosen:
                row["conversion"] = rollout_result(
                    champion, defender, game_ref, str(row["fen"]), leader,
                    depth=args.rollout_depth, movetime=args.rollout_movetime,
                    max_plies=args.max_plies,
                )

            rerank = ranked[0]
            rerank_eval = next(row for row in chosen
                               if ct.board_key(str(row["fen"])) == ct.board_key(str(rerank["fen"])))
            baseline_row = next(row for row in chosen
                                if ct.board_key(str(row["fen"])) == bkey)
            baseline_result = baseline[index]
            rerank_result = str(rerank_eval["conversion"])
            winning_alts = [row for row in chosen
                            if row["conversion"] == "win" and ct.board_key(str(row["fen"])) != bkey]
            parent_id = hashlib.sha256(ct.board_key(parent_fen)).hexdigest()
            split = split_name(parent_id, args.holdout_mod)
            quiet_pair = True
            good = winning_alts[0] if winning_alts else None
            pair_eligible = baseline_result != "win" and good is not None and quiet_pair
            event: dict[str, object] = {
                "schema": 1,
                "index": index,
                "parent_id": parent_id,
                "split": split,
                "parent_fen": parent_fen,
                "leader": leader,
                "baseline_result": baseline_result,
                "baseline_move": str(baseline_child["move"]),
                "baseline_child_fen": str(baseline_child["fen"]),
                "baseline_child_replay": str(baseline_row["conversion"]),
                "decision_score": decision.score,
                "decision_depth": decision.depth,
                "decision_nodes": decision.nodes,
                "verify_depth": args.verify_depth,
                "verify_movetime": args.verify_movetime,
                "top_k": args.top_k,
                "ranked_children": ranked,
                "probed_children": chosen,
                "rerank_move": str(rerank["move"]),
                "rerank_child_fen": str(rerank["fen"]),
                "rerank_result": rerank_result,
                "rerank_changed_move": ct.board_key(str(rerank["fen"])) != bkey,
                "rescue_available": baseline_result != "win" and bool(winning_alts),
                "regression": baseline_result == "win" and rerank_result != "win",
                "hard_pair_eligible": pair_eligible,
            }
            if pair_eligible and good is not None:
                event["good_move"] = str(good["move"])
                event["good_child_fen"] = str(good["fen"])
                event["bad_move"] = str(baseline_child["move"])
                event["bad_child_fen"] = str(baseline_child["fen"])
                buf = pair_buffers[split]
                gf, gt = normalize_move(str(good["move"]))
                bf, bt = normalize_move(str(baseline_child["move"]))
                buf["parents"].append(record)
                buf["good"] += bytes([gf, gt])
                buf["bad"] += bytes([bf, bt])
                buf["pairs"].append(ct.fen_to_record(str(good["fen"]), -1))
                buf["pairs"].append(ct.fen_to_record(str(baseline_child["fen"]), 1))
            events.append(event)
    finally:
        for engine in (root, verifier, champion, defender, apply_ref, game_ref):
            try:
                engine.close()
            except Exception:
                pass

    if not events:
        raise ValueError("no multi-child P3 decisions were processed")

    with (out_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    for split, data in pair_buffers.items():
        split_dir = out_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)
        ct.write_jnnw(split_dir / "parents.jnnw", data["parents"])
        (split_dir / "good_moves.bin").write_bytes(data["good"])
        (split_dir / "bad_moves.bin").write_bytes(data["bad"])
        ct.write_jnnw(split_dir / "immediate_pairs.jnnw", data["pairs"])

    diffs = [
        (1 if event["rerank_result"] == "win" else 0)
        - (1 if event["baseline_result"] == "win" else 0)
        for event in events
    ]
    paired = paired_stats(diffs)
    failures = [event for event in events if event["baseline_result"] != "win"]
    rescues = sum(bool(event["rescue_available"]) for event in failures)
    rerank_rescues = sum(event["baseline_result"] != "win"
                         and event["rerank_result"] == "win" for event in events)
    summary: dict[str, object] = {
        "schema": 1,
        "scope": args.scope,
        "pool": str(args.pool_jnnw),
        "pool_sha256": sha256_file(args.pool_jnnw),
        "baseline_inputs": [str(path) for path in args.baseline_json],
        "pattern_sha256": sha256_file(args.pattern),
        "processed": len(events),
        "baseline_wins": sum(event["baseline_result"] == "win" for event in events),
        "rerank_wins": sum(event["rerank_result"] == "win" for event in events),
        "changed_move": sum(bool(event["rerank_changed_move"]) for event in events),
        "failures": len(failures),
        "rescue_available": rescues,
        "rescue_rate": rescues / len(failures) if failures else None,
        "rerank_rescues": rerank_rescues,
        "rerank_recovery_rate": rerank_rescues / rescues if rescues else None,
        "regressions": sum(bool(event["regression"]) for event in events),
        "hard_pairs": sum(bool(event["hard_pair_eligible"]) for event in events),
        "skipped_capture_parents": skipped_capture_parents,
        "paired": paired,
        "decision_budget": {"depth": args.decision_depth, "movetime": args.decision_movetime},
        "verify_budget": {"depth": args.verify_depth, "movetime": args.verify_movetime},
        "rollout_budget": {"depth": args.rollout_depth, "movetime": args.rollout_movetime},
        "shard": args.shard,
        "nshards": args.nshards,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--defender-jass")
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--defender-pattern", required=True)
    parser.add_argument("--search-params")
    parser.add_argument("--defender-search-params")
    parser.add_argument("--pool-jnnw", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path, nargs="+", required=True)
    parser.add_argument("--scope", choices=("failures", "all"), default="failures")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--decision-depth", type=int)
    decision.add_argument("--decision-movetime", type=float)
    verify = parser.add_mutually_exclusive_group()
    verify.add_argument("--verify-depth", type=int)
    verify.add_argument("--verify-movetime", type=float)
    rollout = parser.add_mutually_exclusive_group()
    rollout.add_argument("--rollout-depth", type=int)
    rollout.add_argument("--rollout-movetime", type=float)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-children", type=int, default=0)
    parser.add_argument("--max-parents", type=int, default=0)
    parser.add_argument("--max-plies", type=int, default=260)
    parser.add_argument("--holdout-mod", type=int, default=5)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.decision_depth is None and args.decision_movetime is None:
        args.decision_depth = 10
    if args.verify_depth is None and args.verify_movetime is None:
        args.verify_depth = 14
    if args.rollout_depth is None and args.rollout_movetime is None:
        args.rollout_depth = 10
    if args.top_k < 1 or args.holdout_mod < 2:
        parser.error("top-k >= 1 and holdout-mod >= 2 required")
    if args.max_children and args.max_children < args.top_k:
        parser.error("max-children must be zero or >= top-k")
    if args.nshards <= 0 or not 0 <= args.shard < args.nshards:
        parser.error("require 0 <= shard < nshards")
    try:
        summary = run(args)
    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
