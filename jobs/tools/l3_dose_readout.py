#!/usr/bin/env python3
"""Readout de l'axe de dose replay, à vues additionnées.

Rupture méthodologique assumée par rapport aux écrans précédents, justifiée par
`docs/experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md` : les vues Q00 et
native estiment la même force (`chi2/ddl = 0,787`, `p ≈ 0,88`), et la native ne
se reproduit même pas à entrées identiques. Exiger la supériorité dans chaque
vue séparément double donc le plancher de bruit sans ajouter d'information.

Ici les deux vues d'un même matchup sont **additionnées** en une seule
estimation, et les vues séparées ne sont conservées que comme diagnostic de
cohérence. Aucun verdict n'autorise de promotion.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

VIEWS = ("q00", "native")

DOSE_BEATS_50 = "REPLAY75_BEATS_TURNOVER50_HUMAN_REVIEW"
DOSE_BELOW_50 = "REPLAY75_BELOW_TURNOVER50_DOSE_AXIS_CLOSED"
DOSE_FLAT = "REPLAY75_FLAT_DOSE_AXIS_CLOSED"
CHAMPION_SUCCESSION = "TURNOVER50_BEATS_F2M_CHAMPION_REVIEW"


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


def checks(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "positive_point_estimate": float(row["rate"]) > 0.5,
        "superiority_established": float(row["ci_low"]) > 0.5,
        "regression_established": float(row["ci_high"]) < 0.5,
    }


def build_readout(
    *,
    force_dir: Path,
    pairs: list[tuple[str, str]],
    games_per_view: int,
) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    per_view: dict[str, Any] = {}
    agreement: dict[str, Any] = {}

    for arm, opponent in pairs:
        key = f"{arm}_vs_{opponent}"
        totals = {"wins_a": 0, "draws": 0, "wins_b": 0}
        views: dict[str, Any] = {}
        for view in VIEWS:
            cell = read_cell(
                force_dir / f"force-{view}-{arm}-vs-{opponent}.json",
                expected_n=games_per_view,
            )
            views[view] = summarize(
                cell["wins_a"], cell["draws"], cell["wins_b"]
            )
            for field in totals:
                totals[field] += cell[field]
        combined[key] = summarize(
            totals["wins_a"], totals["draws"], totals["wins_b"]
        )
        per_view[key] = views
        # diagnostic : les deux vues restent-elles compatibles ?
        gap = views["native"]["rate"] - views["q00"]["rate"]
        se = math.sqrt(
            ((views["q00"]["ci_high"] - views["q00"]["ci_low"]) / 3.92) ** 2
            + ((views["native"]["ci_high"] - views["native"]["ci_low"]) / 3.92) ** 2
        )
        agreement[key] = {
            "native_minus_q00_pp": round(gap * 100, 3),
            "z": round(gap / se, 3) if se > 0 else None,
            "compatible_within_noise": abs(gap / se) < 2.0 if se > 0 else None,
        }

    result_checks = {key: checks(row) for key, row in combined.items()}

    dose_key = "REPLAY75_vs_TURNOVER"
    champion_key = "TURNOVER_vs_F2M"
    dose = result_checks.get(dose_key, {})
    champion = result_checks.get(champion_key, {})

    if dose.get("superiority_established"):
        verdict = DOSE_BEATS_50
        recommendation = "human_review_dose_beyond_50_before_any_promotion"
    elif dose.get("regression_established"):
        verdict = DOSE_BELOW_50
        recommendation = "retain_dose_50_and_close_replay_dose_axis"
    else:
        verdict = DOSE_FLAT
        recommendation = "retain_dose_50_and_close_replay_dose_axis"

    if champion.get("superiority_established"):
        champion_note = CHAMPION_SUCCESSION
    else:
        champion_note = "TURNOVER50_NOT_ESTABLISHED_OVER_F2M"

    return {
        "schema": 1,
        "verdict": verdict,
        "recommendation": recommendation,
        "champion_question": champion_note,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "estimator": {
            "views_summed": True,
            "rationale": "L3_VIEW_AGREEMENT_AND_POWER_20260726",
            "games_per_view_per_cell": games_per_view,
            "games_per_combined_cell": games_per_view * len(VIEWS),
            "smallest_detectable_effect_pp": round(
                196 * math.sqrt(0.25 / (games_per_view * len(VIEWS))), 3
            ),
        },
        "combined_force": combined,
        "combined_checks": result_checks,
        "per_view_force": per_view,
        "view_agreement": agreement,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", type=Path, required=True)
    parser.add_argument("--games-per-view", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    pairs = [
        ("REPLAY75", "TURNOVER"),
        ("REPLAY75", "F2M"),
        ("TURNOVER", "F2M"),
    ]
    report = build_readout(
        force_dir=args.force_dir,
        pairs=pairs,
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
