#!/usr/bin/env python3
"""Aggregate the L3-PURE M0 three-model benchmark and recommend one M1 parent.

The tool is deliberately conservative: M0 can recommend a parent for human
review, but it never authorizes M1, promotion, or an automatic next job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


MIN_GAMES = 500
NONINFERIOR_MARGIN = 0.01
CLEAR_RATE_DELTA = 0.02


def load_gate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("complete"):
        raise ValueError(f"incomplete gate: {path}")
    n = int(payload.get("n", 0))
    if n < MIN_GAMES:
        raise ValueError(f"underpowered gate {path}: n={n} < {MIN_GAMES}")
    for key in ("rate", "ci_low", "ci_high", "elo"):
        if key not in payload:
            raise ValueError(f"{path}: missing {key}")
    rate = float(payload["rate"])
    lo = float(payload["ci_low"])
    hi = float(payload["ci_high"])
    if not (0.0 <= lo <= rate <= hi <= 1.0):
        raise ValueError(f"{path}: invalid interval {lo}, {rate}, {hi}")
    return payload


def compact(gate: dict) -> dict:
    return {
        "wins": int(gate["wins_a"]),
        "draws": int(gate["draws"]),
        "losses": int(gate["wins_b"]),
        "n": int(gate["n"]),
        "rate": float(gate["rate"]),
        "ci95": [float(gate["ci_low"]), float(gate["ci_high"])],
        "elo": float(gate["elo"]),
        "depth": gate.get("depth"),
        "movetime": gate.get("movetime"),
    }


def choose_parent(native: dict[str, dict], q00: dict[str, dict]) -> tuple[str, str]:
    a_g2 = native["c0_a_vs_gen2"]
    p_g2 = native["p1_g4_vs_gen2"]
    p_a = native["p1_g4_vs_c0_a"]
    q_p_a = q00["p1_g4_vs_c0_a"]

    a_rate = float(a_g2["rate"])
    p_rate = float(p_g2["rate"])
    direct_rate = float(p_a["rate"])
    direct_low = float(p_a["ci_low"])
    direct_high = float(p_a["ci_high"])
    q_direct = float(q_p_a["rate"])

    if direct_low > 0.5 and p_rate >= a_rate - NONINFERIOR_MARGIN and q_direct >= 0.5:
        return "M0_RECOMMEND_0842_G4", "direct native superiority; Gen2 non-inferior; Q00 direction supportive"
    if direct_high < 0.5 and a_rate >= p_rate - NONINFERIOR_MARGIN and q_direct <= 0.5:
        return "M0_RECOMMEND_C0_A_G3", "direct native superiority for C0; Gen2 non-inferior; Q00 direction supportive"

    delta = p_rate - a_rate
    if delta >= CLEAR_RATE_DELTA and direct_rate > 0.5 and q_direct >= 0.5:
        return "M0_RECOMMEND_0842_G4", "clear native Gen2-rate lead with both direct views aligned"
    if delta <= -CLEAR_RATE_DELTA and direct_rate < 0.5 and q_direct <= 0.5:
        return "M0_RECOMMEND_C0_A_G3", "clear native Gen2-rate lead for C0 with both direct views aligned"

    return "M0_PARENT_UNRESOLVED_MORE_N_OR_REVIEW", "no pre-registered parent-selection rule was met"


def safe_elo(value: float) -> str:
    sign = "P" if value >= 0 else "M"
    return f"{sign}{abs(value):.1f}".replace(".", "_")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for view in ("historical", "q00", "native"):
        ap.add_argument(f"--{view}-a-gen2", required=True, type=Path)
        ap.add_argument(f"--{view}-p1-gen2", required=True, type=Path)
        ap.add_argument(f"--{view}-p1-a", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--summary-out", required=True, type=Path)
    args = ap.parse_args(argv)

    views: dict[str, dict[str, dict]] = {}
    for view in ("historical", "q00", "native"):
        views[view] = {
            "c0_a_vs_gen2": load_gate(getattr(args, f"{view}_a_gen2")),
            "p1_g4_vs_gen2": load_gate(getattr(args, f"{view}_p1_gen2")),
            "p1_g4_vs_c0_a": load_gate(getattr(args, f"{view}_p1_a")),
        }

    decision, rationale = choose_parent(views["native"], views["q00"])
    recommended_parent = {
        "M0_RECOMMEND_C0_A_G3": "C0_A_G3",
        "M0_RECOMMEND_0842_G4": "P1_0842_G4",
    }.get(decision, "UNRESOLVED")

    payload = {
        "schema": 1,
        "protocol": "L3-PURE-MATURITY-M0-TRIANGLE",
        "decision": decision,
        "recommended_parent_for_human_review": recommended_parent,
        "rationale": rationale,
        "views": {
            view: {name: compact(gate) for name, gate in matches.items()}
            for view, matches in views.items()
        },
        "selection_contract": {
            "minimum_games_per_gate": MIN_GAMES,
            "gen2_noninferiority_margin_rate": NONINFERIOR_MARGIN,
            "clear_rate_delta": CLEAR_RATE_DELTA,
            "primary_view": "native_equal_time_0.3s",
            "supporting_views": ["q00_common_depth9", "historical_0795_depth9"],
        },
        "m1_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    native = payload["views"]["native"]
    summary = {
        "verdict": decision,
        "recommended_parent": recommended_parent,
        "c0_a_native_elo_vs_gen2": native["c0_a_vs_gen2"]["elo"],
        "p1_0842_native_elo_vs_gen2": native["p1_g4_vs_gen2"]["elo"],
        "p1_0842_native_elo_vs_c0_a": native["p1_g4_vs_c0_a"]["elo"],
        "m1_authorized": False,
        "result_file": "m0-triangle-verdict.json",
    }
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(decision)
    print(f"recommended_parent={recommended_parent}")
    print(f"c0_a_native_elo_vs_gen2={native['c0_a_vs_gen2']['elo']}")
    print(f"p1_0842_native_elo_vs_gen2={native['p1_g4_vs_gen2']['elo']}")
    print(f"p1_0842_native_elo_vs_c0_a={native['p1_g4_vs_c0_a']['elo']}")
    print("markers=" + ",".join([
        f"VERDICT__{decision}",
        f"RECOMMENDED_PARENT__{recommended_parent}",
        f"C0_A_NATIVE_ELO_VS_GEN2__{safe_elo(native['c0_a_vs_gen2']['elo'])}",
        f"P1_0842_NATIVE_ELO_VS_GEN2__{safe_elo(native['p1_g4_vs_gen2']['elo'])}",
        f"P1_0842_NATIVE_ELO_VS_C0_A__{safe_elo(native['p1_g4_vs_c0_a']['elo'])}",
        "M1_AUTHORIZED__FALSE",
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
