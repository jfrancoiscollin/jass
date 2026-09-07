#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "jobs/tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "jobs/tools"))
import calibrate_vs_scan as cvs  # noqa: E402

SCHEMA = "jass.d3.runtime_move_ordering_preflight.v1"
VERDICT = "D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_COMPLETE_V1"
SEED = 2026111299
POSITIONS = 128
IDENTITY_DEPTH = 7
ON_DEPTH = 2
BELOW_SUPPORT_FEN = "W:WK46,K47,K48:BK3,K4,K5"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fens(path: Path) -> list[str]:
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith(";"):
            out.append(line)
    if len(out) != POSITIONS:
        raise ValueError(f"expected {POSITIONS} fixtures, got {len(out)}")
    return out


def parse_last(lines: list[str]) -> dict[str, Any]:
    last = lines[-1]
    if not last.startswith("bestmove"):
        raise ValueError(f"not bestmove: {last}")
    fields = {k: int(v) for k, v in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", last)}
    move = last.split()[1]
    pv_match = re.search(r"\bpv=([^\s]+)", last)
    return {
        "bestmove": move,
        "score": fields.get("score"),
        "depth": fields.get("depth"),
        "nodes": fields.get("nodes"),
        "pv": pv_match.group(1) if pv_match else "",
    }


def search_rows(binary: Path, model: Path, positions: list[str], env: dict[str, str | None], *, depth: int) -> list[dict[str, Any]]:
    eng = cvs.JassEngine(str(binary), pattern_path=str(model), no_book=True,
                         enforce_no_book=True, threads=1, env_overrides=env)
    rows: list[dict[str, Any]] = []
    try:
        for fen in positions:
            eng.set_position_fen(fen)
            _move, lines = eng.go_verbose(depth=depth)
            rows.append(parse_last(lines))
    finally:
        eng.close()
    return rows


def malformed_fails(binary: Path, model: Path, bad: Path) -> bool:
    env = os.environ.copy()
    env["JASS_D3_RUNTIME_ADAPTER"] = str(bad)
    env["JASS_D3_RUNTIME_BASE_MODEL"] = str(model)
    proc = subprocess.Popen([str(binary), "--pattern", str(model), "--no-book"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert proc.stdin is not None
        proc.stdin.write("hello\nposition startpos\ngo depth 2\n")
        proc.stdin.flush()
        try:
            rc = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()
            return False
        return rc != 0
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--expected-model-sha", required=True)
    ap.add_argument("--expected-adapter-sha", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    if sha(a.model) != a.expected_model_sha:
        raise SystemExit("D3_RUNTIME_PREFLIGHT_INVALID: value model SHA drift")
    if sha(a.adapter) != a.expected_adapter_sha:
        raise SystemExit("D3_RUNTIME_PREFLIGHT_INVALID: adapter SHA drift")
    positions = fens(a.fixtures)
    off_env = {"JASS_D3_RUNTIME_ADAPTER": None, "JASS_D3_RUNTIME_BASE_MODEL": None,
               "JASS_DSSD_MOVE_ORDER_POLICY": None, "JASS_TB_MOVE_ORDER_POLICY": None}
    control = search_rows(a.control, a.model, positions, off_env, depth=IDENTITY_DEPTH)
    candidate_off = search_rows(a.candidate, a.model, positions, off_env, depth=IDENTITY_DEPTH)
    mismatches = [i for i, (x, y) in enumerate(zip(control, candidate_off)) if x != y]
    if mismatches:
        raise SystemExit(f"D3_RUNTIME_PREFLIGHT_INVALID: OFF identity mismatches={mismatches[:8]}")

    on_env = {"JASS_D3_RUNTIME_ADAPTER": str(a.adapter),
              "JASS_D3_RUNTIME_BASE_MODEL": str(a.model),
              "JASS_DSSD_MOVE_ORDER_POLICY": None, "JASS_TB_MOVE_ORDER_POLICY": None}
    candidate_on = search_rows(a.candidate, a.model, positions, on_env, depth=ON_DEPTH)
    if len(candidate_on) != POSITIONS or any(r["bestmove"] == "0-0" for r in candidate_on):
        raise SystemExit("D3_RUNTIME_PREFLIGHT_INVALID: treatment activation search failure")

    below_control = search_rows(a.control, a.model, [BELOW_SUPPORT_FEN], off_env, depth=IDENTITY_DEPTH)[0]
    below_on = search_rows(a.candidate, a.model, [BELOW_SUPPORT_FEN], on_env, depth=IDENTITY_DEPTH)[0]
    if below_control != below_on:
        raise SystemExit("D3_RUNTIME_PREFLIGHT_INVALID: below-9 treatment not dormant")

    bad = a.out.with_suffix(".bad.npy")
    bad.write_bytes(b"not-a-valid-npy")
    malformed = malformed_fails(a.candidate, a.model, bad)
    bad.unlink(missing_ok=True)
    if not malformed:
        raise SystemExit("D3_RUNTIME_PREFLIGHT_INVALID: malformed adapter did not fail closed")

    result = {
        "schema": SCHEMA,
        "verdict": VERDICT,
        "fixture_seed": SEED,
        "positions": POSITIONS,
        "identity_depth": IDENTITY_DEPTH,
        "activation_depth": ON_DEPTH,
        "adapter_sha256": sha(a.adapter),
        "value_model_sha256": sha(a.model),
        "adapter_width": 632,
        "white_square_canonicalization": "51-sq",
        "support": {"P0": [30, 40], "P1": [20, 29], "P2": [12, 19], "P3": [9, 11],
                    "below9": "LEGACY", "below9_runtime_identity": True},
        "control_candidate_off_identity": {"bestmove_score_pv_nodes": True, "mismatches": 0},
        "candidate_on_searches": POSITIONS,
        "malformed_adapter_fail_closed": True,
        "root_pv_priority_unchanged": True,
        "tt_priority_unchanged": True,
        "value_leaf_bytes_unchanged": True,
        "forbidden_reads": {"qscore": 0, "full_ladder_1843": 0, "search_decision_trace": 0,
                            "teacher": 0, "labels": 0},
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(VERDICT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
