#!/usr/bin/env python3
"""D3 runtime equal-node paired-color game runner.

Uses the production referee/match plumbing from calibrate_vs_scan, but replaces
Jass's search command with the preregistered exact 20,000-node limit. Engine
errors are exceptions: they are never scored as losses or draws.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "jobs" / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "jobs" / "tools"))

import calibrate_vs_scan as cvs

NODE_BUDGET = 20000
MAX_PLIES = 160


class ExactNodeJass(cvs.JassEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_telemetry["d3_feature_calls"] = 0

    def go_verbose(self, depth=None, movetime=None):
        if depth is not None or movetime is not None:
            raise ValueError("D3 equal-node accepts only its frozen exact-node limit")
        self._drain()
        started = time.monotonic()
        self._send(f"go nodes {NODE_BUDGET}")
        lines = self._read_until(
            lambda line: line.startswith("bestmove") or line.startswith("error"),
            timeout_s=60.0,
        )
        last = lines[-1]
        if last.startswith("error"):
            raise cvs.EngineFailure(f"{self.label}: {last}")
        elapsed = time.monotonic() - started
        fields = {
            key: int(value)
            for key, value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", last)
        }
        nodes = fields.get("nodes", -1)
        if nodes < 0 or nodes > NODE_BUDGET:
            raise cvs.EngineFailure(
                f"{self.label}: exact-node receipt outside [0,{NODE_BUDGET}]: {nodes}"
            )
        self.search_telemetry["searches"] += 1
        self.search_telemetry["depth_sum"] += fields.get("depth", 0)
        self.search_depths[fields.get("depth", 0)] += 1
        self.search_telemetry["nodes"] += nodes
        self.search_telemetry["eval_calls"] += fields.get("evalcalls", 0)
        self.search_telemetry["wall_seconds"] += elapsed
        self.search_telemetry["d3_feature_calls"] += fields.get("d3calls", 0)
        return cvs.parse_jass_bestmove(last), lines


def snapshot(engine: ExactNodeJass) -> dict:
    return dict(engine.search_telemetry)


def delta(after: dict, before: dict) -> dict:
    out = {}
    for key in ("searches", "depth_sum", "nodes", "eval_calls", "wall_seconds",
                "d3_feature_calls"):
        out[key] = after.get(key, 0) - before.get(key, 0)
    out["mean_completed_depth"] = (
        out["depth_sum"] / out["searches"] if out["searches"] else 0.0
    )
    return out


def score_from_white(outcome: str, candidate_is_white: bool) -> float:
    if outcome == "D":
        return 0.5
    white_score = 1.0 if outcome == "W" else 0.0
    return white_score if candidate_is_white else 1.0 - white_score


def wdl_from_candidate(outcome: str, candidate_is_white: bool) -> str:
    score = score_from_white(outcome, candidate_is_white)
    return "W" if score == 1.0 else "D" if score == 0.5 else "L"


def make_engine(path: str, label: str, model: str, *, candidate: bool, adapter: str) -> ExactNodeJass:
    env = {
        "JASS_D3_RUNTIME_ADAPTER": adapter if candidate else None,
        "JASS_D3_RUNTIME_BASE_MODEL": model if candidate else None,
        "JASS_DSSD_MOVE_ORDER_POLICY": None,
        "JASS_TB_MOVE_ORDER_POLICY": None,
    }
    return ExactNodeJass(
        path, label=label, pattern_path=model, threads=1,
        no_book=True, enforce_no_book=True, env_overrides=env,
    )


def play_pair(opening: str, index: int, mode: str, control_path: str,
              candidate_path: str, model: str, adapter: str,
              control_a: ExactNodeJass, control_b: ExactNodeJass,
              candidate: ExactNodeJass | None, referee: cvs.Referee) -> dict:
    if mode == "primary":
        assert candidate is not None
        before_c = snapshot(candidate); before_k = snapshot(control_a)
        g1 = cvs.play_game(candidate, control_a, referee, opening,
                           max_plies=MAX_PLIES, game_timeout_s=None)
        mid_c = snapshot(candidate); mid_k = snapshot(control_a)
        g2 = cvs.play_game(control_a, candidate, referee, opening,
                           max_plies=MAX_PLIES, game_timeout_s=None)
        after_c = snapshot(candidate); after_k = snapshot(control_a)
        scores = [score_from_white(g1.outcome, True), score_from_white(g2.outcome, False)]
        return {
            "schema": "jass.d3.runtime_equal_node.game_pair.v1",
            "mode": mode, "opening_index": index, "fen": opening,
            "node_budget": NODE_BUDGET, "max_plies": MAX_PLIES,
            "games": [
                {"d3_color": "white", "outcome_white": g1.outcome,
                 "d3_wdl": wdl_from_candidate(g1.outcome, True),
                 "d3_score": scores[0], "plies": g1.plies, "reason": g1.reason,
                 "d3_telemetry": delta(mid_c, before_c),
                 "control_telemetry": delta(mid_k, before_k)},
                {"d3_color": "black", "outcome_white": g2.outcome,
                 "d3_wdl": wdl_from_candidate(g2.outcome, False),
                 "d3_score": scores[1], "plies": g2.plies, "reason": g2.reason,
                 "d3_telemetry": delta(after_c, mid_c),
                 "control_telemetry": delta(after_k, mid_k)},
            ],
            "pair_score_d3": sum(scores) / 2.0,
        }

    before_a = snapshot(control_a); before_b = snapshot(control_b)
    g1 = cvs.play_game(control_a, control_b, referee, opening,
                       max_plies=MAX_PLIES, game_timeout_s=None)
    mid_a = snapshot(control_a); mid_b = snapshot(control_b)
    g2 = cvs.play_game(control_b, control_a, referee, opening,
                       max_plies=MAX_PLIES, game_timeout_s=None)
    after_a = snapshot(control_a); after_b = snapshot(control_b)
    scores = [score_from_white(g1.outcome, True), score_from_white(g2.outcome, False)]
    return {
        "schema": "jass.d3.runtime_equal_node.game_pair.v1",
        "mode": mode, "opening_index": index, "fen": opening,
        "node_budget": NODE_BUDGET, "max_plies": MAX_PLIES,
        "games": [
            {"arm_a_color": "white", "outcome_white": g1.outcome,
             "arm_a_score": scores[0], "plies": g1.plies, "reason": g1.reason,
             "arm_a_telemetry": delta(mid_a, before_a),
             "arm_b_telemetry": delta(mid_b, before_b)},
            {"arm_a_color": "black", "outcome_white": g2.outcome,
             "arm_a_score": scores[1], "plies": g2.plies, "reason": g2.reason,
             "arm_a_telemetry": delta(after_a, mid_a),
             "arm_b_telemetry": delta(after_b, mid_b)},
        ],
        "pair_score_arm_a": sum(scores) / 2.0,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("primary", "harness"), required=True)
    p.add_argument("--openings", type=Path, required=True)
    p.add_argument("--start", type=int, required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--out-games", type=Path, required=True)
    p.add_argument("--out-report", type=Path, required=True)
    a = p.parse_args()

    openings = [line.strip() for line in a.openings.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    selected = openings[a.start:a.start + a.count]
    if len(selected) != a.count:
        raise ValueError("shard range outside opening pool")

    control_a = make_engine(a.control, "CONTROL_A", a.model, candidate=False, adapter=a.adapter)
    control_b = make_engine(a.control, "CONTROL_B", a.model, candidate=False, adapter=a.adapter)
    candidate = (make_engine(a.candidate, "D3", a.model, candidate=True, adapter=a.adapter)
                 if a.mode == "primary" else None)
    referee = cvs.Referee(a.control)
    rows = []
    try:
        for local, opening in enumerate(selected):
            rows.append(play_pair(
                opening, a.start + local, a.mode, a.control, a.candidate,
                a.model, a.adapter, control_a, control_b, candidate, referee
            ))
    finally:
        if candidate is not None:
            candidate.close()
        control_a.close(); control_b.close(); referee.close()

    a.out_games.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    report = {
        "schema": "jass.d3.runtime_equal_node.shard.v1",
        "mode": a.mode, "start": a.start, "openings": len(rows),
        "games": 2 * len(rows), "node_budget": NODE_BUDGET,
        "max_plies": MAX_PLIES, "skipped": 0, "engine_failures": 0,
    }
    a.out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
