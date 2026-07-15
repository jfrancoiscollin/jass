#!/usr/bin/env python3
"""Promotion inter-tours de la sonde v3.2.

Régimes :
  --regime young
      T1-bis -> T3. La conversion est tracée mais non exigée. Le candidat
      est rejeté si une régression est établie contre le parent OU contre
      la référence fixe. Une comparaison absente/incomplète est un échec
      technique et ne peut jamais produire ``promotion_decision=promote``.

  --regime established
      Post-sonde. Promotion seulement si le généraliste reste non-régressif
      et si la conversion monte sur la fenêtre pré-engagée.

Le module est volontairement pur : il transforme des W/D/L ou statistiques
pré-calculées en un manifest JSON reproductible.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

YOUNG_TOURS = ("T1-bis", "T2", "T3")


def ci_from_wdl(a: int, d: int, b: int, z: float = 1.96) -> dict:
    """IC normal du taux de score, identique au harnais DOE."""
    n = a + d + b
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None, "n": 0}
    r = (a + 0.5 * d) / n
    var = max(0.0, (a + 0.25 * d) / n - r * r)
    se = math.sqrt(var / n)
    return {
        "rate": round(r, 6),
        "ci_low": round(max(0.0, r - z * se), 6),
        "ci_high": round(min(1.0, r + z * se), 6),
        "n": n,
    }


def _match_stats(match: dict) -> dict:
    """Accepte {wins_a, draws, wins_b} ou des stats déjà calculées."""
    if "wins_a" in match or "wins_b" in match or "draws" in match:
        return ci_from_wdl(
            int(match.get("wins_a", 0)),
            int(match.get("draws", 0)),
            int(match.get("wins_b", 0)),
        )
    return {
        "rate": match.get("rate"),
        "ci_low": match.get("ci_low"),
        "ci_high": match.get("ci_high"),
        "n": int(match.get("n", 0)),
    }


def _young_decision_one(stats: dict) -> str:
    """Retourne pass, reject ou technical.

    Fail-closed : n=0, IC absent ou non numérique = technical. Une régression
    est établie seulement si la borne haute est strictement sous 0,5.
    """
    if int(stats.get("n", 0)) <= 0:
        return "technical"
    ci_high = stats.get("ci_high")
    if ci_high is None:
        return "technical"
    try:
        value = float(ci_high)
    except (TypeError, ValueError):
        return "technical"
    return "reject" if value < 0.5 else "pass"


def young_gate(
    vs_parent: dict,
    vs_fixed: dict,
    tour: str,
    conversion: dict | None = None,
) -> dict:
    reasons: list[str] = []
    if tour not in YOUNG_TOURS:
        reasons.append(f"tour {tour!r} interdit en régime jeune (autorisés: {YOUNG_TOURS})")

    parent_stats = _match_stats(vs_parent)
    fixed_stats = _match_stats(vs_fixed)
    parent_decision = _young_decision_one(parent_stats)
    fixed_decision = _young_decision_one(fixed_stats)

    if parent_decision == "technical":
        reasons.append("vs_parent incomplet : n=0 ou intervalle absent")
    elif parent_decision == "reject":
        reasons.append(
            f"RÉGRESSION établie vs parent (ci_high={parent_stats['ci_high']} < 0.5)"
        )

    if fixed_decision == "technical":
        reasons.append("vs_fixed_reference incomplet : n=0 ou intervalle absent")
    elif fixed_decision == "reject":
        reasons.append(
            "RÉGRESSION établie vs référence fixe "
            f"(ci_high={fixed_stats['ci_high']} < 0.5)"
        )

    technical = (
        tour not in YOUNG_TOURS
        or parent_decision == "technical"
        or fixed_decision == "technical"
    )
    regression = parent_decision == "reject" or fixed_decision == "reject"
    promote = not technical and not regression

    if technical:
        status = "stop_technical"
    elif regression:
        status = "stop_regression"
    elif tour == "T3":
        status = "complete_probe"
    else:
        status = "continue_probe"

    return _manifest(
        "young",
        tour,
        parent_stats,
        fixed_stats,
        parent_decision,
        fixed_decision,
        "promote" if promote else "reject",
        status,
        reasons,
        conversion,
    )


def established_gate(
    vs_parent: dict,
    vs_fixed: dict,
    tour: str,
    conversion_window: list[float],
    conv_min_delta: float,
    window: int,
    conversion: dict | None = None,
) -> dict:
    reasons: list[str] = []
    parent_stats = _match_stats(vs_parent)
    fixed_stats = _match_stats(vs_fixed)
    parent_decision = _young_decision_one(parent_stats)
    fixed_decision = _young_decision_one(fixed_stats)

    technical = "technical" in (parent_decision, fixed_decision)
    nonreg = parent_decision == "pass" and fixed_decision == "pass"
    if technical:
        reasons.append("comparaison généraliste incomplète")
    elif not nonreg:
        reasons.append("régression généraliste établie")

    conv_ok = False
    if len(conversion_window) >= window:
        delta = conversion_window[-1] - conversion_window[-window]
        conv_ok = delta >= conv_min_delta
        reasons.append(
            f"conversion Δ({window} tours)={delta:+.4f} vs seuil {conv_min_delta:+.4f}"
        )
    else:
        reasons.append(
            f"fenêtre conversion insuffisante ({len(conversion_window)}<{window})"
        )

    promote = nonreg and conv_ok and not technical
    if technical:
        status = "stop_technical"
    elif not nonreg:
        status = "stop_regression"
    else:
        status = "complete_probe" if promote else "continue_probe"

    return _manifest(
        "established",
        tour,
        parent_stats,
        fixed_stats,
        parent_decision,
        fixed_decision,
        "promote" if promote else "reject",
        status,
        reasons,
        conversion,
    )


def _manifest(
    regime: str,
    tour: str,
    parent_stats: dict,
    fixed_stats: dict,
    parent_decision: str,
    fixed_decision: str,
    decision: str,
    status: str,
    reasons: list[str],
    conversion: dict | None,
) -> dict:
    conv = conversion or {}
    return {
        "regime": regime,
        "tour": tour,
        "candidate_sha": conv.get("_candidate_sha", "..."),
        "parent_sha": conv.get("_parent_sha", "..."),
        "fixed_reference_sha": conv.get("_fixed_reference_sha", "..."),
        "vs_parent": {**parent_stats, "decision": parent_decision},
        "vs_fixed_reference": {**fixed_stats, "decision": fixed_decision},
        "conversion": {
            "global": conv.get("global"),
            "p1_net": conv.get("p1_net"),
            "p2_moyen": conv.get("p2_moyen"),
            "p3_mince": conv.get("p3_mince"),
            "p4_egal": conv.get("p4_egal"),
        },
        "promotion_decision": decision,
        "scientific_status": status,
        "reasons": reasons,
    }


def _cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regime", required=True, choices=["young", "established"])
    parser.add_argument("--tour", required=True)
    parser.add_argument(
        "--input",
        required=True,
        help="JSON {vs_parent, vs_fixed_reference, conversion?, conversion_window?}",
    )
    parser.add_argument("--out")
    parser.add_argument("--conv-min-delta", type=float, default=0.02)
    parser.add_argument("--conv-window", type=int, default=2)
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text())
    vs_parent = data["vs_parent"]
    vs_fixed = data["vs_fixed_reference"]
    conversion = data.get("conversion")
    if args.regime == "young":
        manifest = young_gate(vs_parent, vs_fixed, args.tour, conversion)
    else:
        manifest = established_gate(
            vs_parent,
            vs_fixed,
            args.tour,
            data.get("conversion_window", []),
            args.conv_min_delta,
            args.conv_window,
            conversion,
        )

    if args.out:
        Path(args.out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, ensure_ascii=False))
    if manifest["scientific_status"] == "stop_technical":
        return 2
    return 0 if manifest["promotion_decision"] == "promote" else 3


if __name__ == "__main__":
    sys.exit(_cli())
