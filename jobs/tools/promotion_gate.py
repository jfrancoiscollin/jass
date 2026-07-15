#!/usr/bin/env python3
"""Phase 0 (spec codex_review_v3_2 §4) — gate de promotion inter-tours à deux
régimes explicites.

  --regime young        : sonde T1-bis→T3. Promotion autorisée sauf RÉGRESSION
                          STATISTIQUEMENT ÉTABLIE (borne HAUTE de l'IC du taux
                          < 0.500) contre le parent OU contre la référence
                          fixe. Neutre/incertain = promotion autorisée. La
                          conversion est MESURÉE mais PAS exigée.
  --regime established   : post-sonde. Promotion = généraliste non-régressif ET
                          conversion en HAUSSE sur une fenêtre de 2 tours (marge
                          + fenêtre pré-engagées).

Sortie = manifest JSON §4.4. Le régime jeune est réservé à {T1-bis, T2, T3}.
Module PUR (stats seules) → testable.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

YOUNG_TOURS = ("T1-bis", "T2", "T3")


def ci_from_wdl(a: int, d: int, b: int, z: float = 1.96) -> dict:
    """IC normal-approx du taux de score (a=wins cand, d=draws, b=wins adverse).
    Identique au harnais jass_vs_jass_arch / DOE 0726."""
    n = a + d + b
    if n <= 0:
        return {"rate": None, "ci_low": None, "ci_high": None, "n": 0}
    r = (a + 0.5 * d) / n
    var = max(0.0, (a + 0.25 * d) / n - r * r)
    se = math.sqrt(var / n)
    return {"rate": round(r, 6), "ci_low": round(max(0.0, r - z * se), 6),
            "ci_high": round(min(1.0, r + z * se), 6), "n": n}


def _match_stats(m: dict) -> dict:
    """Accepte soit {wins_a,draws,wins_b} soit {rate,ci_low,ci_high,n} déjà calculé."""
    if "wins_a" in m or "wins_b" in m or "draws" in m:
        return ci_from_wdl(int(m.get("wins_a", 0)), int(m.get("draws", 0)), int(m.get("wins_b", 0)))
    return {"rate": m.get("rate"), "ci_low": m.get("ci_low"),
            "ci_high": m.get("ci_high"), "n": int(m.get("n", 0))}


def _young_decision_one(stats: dict) -> str:
    """REJET ssi borne HAUTE strictement < 0.5 (régression établie). Sinon pass.
    n=0 = pas de preuve de régression → pass (mais signalé côté reasons)."""
    ch = stats.get("ci_high")
    if ch is None:
        return "pass"                    # pas de données = pas de régression établie
    return "reject" if ch < 0.5 else "pass"


def young_gate(vs_parent: dict, vs_fixed: dict, tour: str,
               conversion: dict | None = None) -> dict:
    reasons: list[str] = []
    if tour not in YOUNG_TOURS:
        reasons.append(f"tour {tour!r} interdit en régime jeune (autorisés: {YOUNG_TOURS})")
    sp = _match_stats(vs_parent); sf = _match_stats(vs_fixed)
    dp = _young_decision_one(sp); df = _young_decision_one(sf)
    if sp["n"] == 0:
        reasons.append("vs_parent n=0 (jauge incomplète ?)")
    if sf["n"] == 0:
        reasons.append("vs_fixed_reference n=0 (jauge incomplète ?)")
    promote = (tour in YOUNG_TOURS) and dp == "pass" and df == "pass"
    if dp == "reject":
        reasons.append(f"RÉGRESSION établie vs parent (ci_high={sp['ci_high']} < 0.5)")
    if df == "reject":
        reasons.append(f"RÉGRESSION établie vs référence fixe (ci_high={sf['ci_high']} < 0.5)")
    # statut scientifique
    if tour not in YOUNG_TOURS:
        status = "stop_technical"
    elif dp == "reject" or df == "reject":
        status = "stop_regression"
    elif sp["n"] == 0 or sf["n"] == 0:
        status = "stop_technical"
    elif tour == "T3":
        status = "complete_probe"
    else:
        status = "continue_probe"
    return _manifest("young", tour, sp, sf, dp, df,
                     "promote" if promote else "reject", status, reasons, conversion)


def established_gate(vs_parent: dict, vs_fixed: dict, tour: str,
                     conversion_window: list[float], conv_min_delta: float,
                     window: int, conversion: dict | None = None) -> dict:
    """Post-sonde : non-régressif ET conversion en hausse sur `window` tours."""
    reasons: list[str] = []
    sp = _match_stats(vs_parent); sf = _match_stats(vs_fixed)
    nonreg = _young_decision_one(sp) == "pass" and _young_decision_one(sf) == "pass"
    if not nonreg:
        reasons.append("régression généraliste établie")
    conv_ok = False
    if len(conversion_window) >= window:
        delta = conversion_window[-1] - conversion_window[-window]
        conv_ok = delta >= conv_min_delta
        reasons.append(f"conversion Δ({window} tours)={delta:+.4f} vs seuil {conv_min_delta:+.4f}")
    else:
        reasons.append(f"fenêtre conversion insuffisante ({len(conversion_window)}<{window})")
    promote = nonreg and conv_ok
    status = "stop_regression" if not nonreg else ("complete_probe" if promote else "continue_probe")
    return _manifest("established", tour, sp, sf,
                     "pass" if nonreg else "reject", "pass" if nonreg else "reject",
                     "promote" if promote else "reject", status, reasons, conversion)


def _manifest(regime, tour, sp, sf, dp, df, decision, status, reasons, conversion) -> dict:
    conv = conversion or {}
    return {
        "regime": regime, "tour": tour,
        "candidate_sha": conv.get("_candidate_sha", "..."),
        "parent_sha": conv.get("_parent_sha", "..."),
        "fixed_reference_sha": conv.get("_fixed_reference_sha", "..."),
        "vs_parent": {**sp, "decision": dp},
        "vs_fixed_reference": {**sf, "decision": df},
        "conversion": {
            "global": conv.get("global", 0.0),
            "p1_net": conv.get("p1_net", 0.0), "p2_moyen": conv.get("p2_moyen", 0.0),
            "p3_mince": conv.get("p3_mince", 0.0), "p4_egal": conv.get("p4_egal", 0.0),
        },
        "promotion_decision": decision,
        "scientific_status": status,
        "reasons": reasons,
    }


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regime", required=True, choices=["young", "established"])
    ap.add_argument("--tour", required=True)
    ap.add_argument("--input", required=True, help="JSON {vs_parent, vs_fixed_reference, conversion?, conversion_window?}")
    ap.add_argument("--out")
    ap.add_argument("--conv-min-delta", type=float, default=0.02)
    ap.add_argument("--conv-window", type=int, default=2)
    a = ap.parse_args(argv)
    data = json.loads(Path(a.input).read_text())
    vp = data["vs_parent"]; vf = data["vs_fixed_reference"]; conv = data.get("conversion")
    if a.regime == "young":
        man = young_gate(vp, vf, a.tour, conv)
    else:
        man = established_gate(vp, vf, a.tour, data.get("conversion_window", []),
                               a.conv_min_delta, a.conv_window, conv)
    if a.out:
        Path(a.out).write_text(json.dumps(man, indent=2, ensure_ascii=False))
    print(json.dumps(man, ensure_ascii=False))
    # exit code : 0 promote, 3 reject, 2 technique
    return {"promote": 0, "reject": 3}.get(man["promotion_decision"], 2) if man["scientific_status"] != "stop_technical" else 2


if __name__ == "__main__":
    sys.exit(_cli())
