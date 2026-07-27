#!/usr/bin/env python3
"""Porte de succession de champion : TURNOVER contre F2M.

Trois conditions, toutes préenregistrées, doivent tenir simultanément :

1. **force** — TURNOVER établit sa supériorité sur F2M sur le pool neuf, vues
   additionnées, borne basse à 95 % au-dessus de 50 % ;
2. **garde historique** — aucune régression établie contre Gen2 ;
3. **conversion** — P3 et P4 au-dessus du plancher absolu, sans effondrement.

Aucun verdict n'autorise de promotion. Une succession est une décision humaine ;
cette porte ne fait que la recommander ou la refuser.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

VIEWS = ("q00", "native")
ARM = "TURNOVER"
INCUMBENT = "F2M"
HISTORICAL = "GEN2"
STRATA = ("p3_mince", "p4_egal")

RECOMMEND = "TURNOVER_SUCCESSION_RECOMMENDED_HUMAN_REVIEW"
GUARD_FAIL = "TURNOVER_SUCCESSION_BLOCKED_GUARDRAIL"
FORCE_FAIL = "TURNOVER_SUCCESSION_NOT_ESTABLISHED_ON_FRESH_POOL"

CONVERSION_FLOOR = 0.95


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def summarize(wins: int, draws: int, losses: int) -> dict[str, Any]:
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("cellule vide")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    return {
        "wins_a": wins,
        "draws": draws,
        "wins_b": losses,
        "n": n,
        "rate": round(rate, 6),
        "ci_low": round(max(0.0, rate - 1.96 * se), 6),
        "ci_high": round(min(1.0, rate + 1.96 * se), 6),
        "elo": round(-400 * math.log10(1 / rate - 1), 2) if 0 < rate < 1 else 0.0,
    }


def read_cell(path: Path, *, expected_n: int) -> dict[str, int]:
    value = load(path)
    wins, draws, losses = (
        int(value["wins_a"]),
        int(value["draws"]),
        int(value["wins_b"]),
    )
    if int(value["n"]) != expected_n or wins + draws + losses != expected_n:
        raise ValueError(f"{path}: attendu {expected_n} parties complètes")
    if value.get("complete") is not True:
        raise ValueError(f"{path}: cellule incomplète")
    return {"wins_a": wins, "draws": draws, "wins_b": losses}


def combined(force_dir: Path, opponent: str, games_per_view: int) -> dict[str, Any]:
    totals = {"wins_a": 0, "draws": 0, "wins_b": 0}
    views = {}
    for view in VIEWS:
        cell = read_cell(
            force_dir / f"force-{view}-{ARM}-vs-{opponent}.json",
            expected_n=games_per_view,
        )
        views[view] = summarize(cell["wins_a"], cell["draws"], cell["wins_b"])
        for field in totals:
            totals[field] += cell[field]
    result = summarize(totals["wins_a"], totals["draws"], totals["wins_b"])
    result["per_view"] = views
    return result


def build_gate(
    *,
    force_dir: Path,
    conversion_dir: Path,
    dose_readout: dict[str, Any],
    openings: dict[str, Any],
    games_per_view: int,
) -> dict[str, Any]:
    if dose_readout.get("champion_question") != "TURNOVER50_BEATS_F2M_CHAMPION_REVIEW":
        raise ValueError("le readout de dose n'a pas établi TURNOVER sur F2M")

    primary = combined(force_dir, INCUMBENT, games_per_view)
    guard = combined(force_dir, HISTORICAL, games_per_view)

    conversion: dict[str, Any] = {}
    for stratum in STRATA:
        report = load(conversion_dir / f"{ARM}-{stratum}.json")
        rate = float(report["conversion"])
        conversion[stratum] = {
            "conversion": round(rate, 6),
            "n_pos": int(report["n_pos"]),
            "above_floor": rate >= CONVERSION_FLOOR,
        }

    force_established = float(primary["ci_low"]) > 0.5
    guard_ok = float(guard["ci_high"]) >= 0.5
    conversion_ok = all(v["above_floor"] for v in conversion.values())

    guardrails = {
        "fresh_pool_superiority_over_incumbent": force_established,
        "historical_reference_no_established_regression": guard_ok,
        "p3_mince_absolute_conversion_floor": conversion[STRATA[0]]["above_floor"],
        "p4_egal_absolute_conversion_floor": conversion[STRATA[1]]["above_floor"],
        "independent_pool_disjoint": int(openings.get("overlap_records", -1)) == 0,
    }
    all_pass = all(guardrails.values())

    if not force_established:
        verdict = FORCE_FAIL
        recommendation = "retain_f2m_as_general_champion"
    elif not all_pass:
        verdict = GUARD_FAIL
        recommendation = "retain_f2m_until_failing_guardrail_is_understood"
    else:
        verdict = RECOMMEND
        recommendation = "human_review_champion_succession_then_deliberate_bake"

    return {
        "schema": 1,
        "verdict": verdict,
        "recommendation": recommendation,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "all_guardrails_pass": all_pass,
        "guardrails": guardrails,
        "protocol": {
            "candidate": ARM,
            "incumbent": INCUMBENT,
            "historical_reference": HISTORICAL,
            "views_summed": True,
            "games_per_view_per_cell": games_per_view,
            "games_per_combined_cell": games_per_view * len(VIEWS),
            "smallest_detectable_effect_pp": round(
                196 * math.sqrt(0.25 / (games_per_view * len(VIEWS))), 3
            ),
            "conversion_floor": CONVERSION_FLOOR,
        },
        "primary_vs_incumbent": primary,
        "guard_vs_historical": guard,
        "conversion": conversion,
        "opening_manifest": openings,
        "prior_evidence": {
            "job": "home-0993",
            "cell": dose_readout.get("combined_force", {}).get("TURNOVER_vs_F2M", {}),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", type=Path, required=True)
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--dose-readout", type=Path, required=True)
    parser.add_argument("--opening-manifest", type=Path, required=True)
    parser.add_argument("--expected-opening-seed", type=int, required=True)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--games-per-view", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    openings = load(args.opening_manifest)
    if (
        openings.get("sha256") != args.expected_opening_sha256
        or openings.get("generator_seed") != args.expected_opening_seed
    ):
        raise SystemExit("opening pool identity drift")

    report = build_gate(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        dose_readout=load(args.dose_readout),
        openings=openings,
        games_per_view=args.games_per_view,
    )
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.summary_out:
        args.summary_out.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
    print(report["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
