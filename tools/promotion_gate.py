#!/usr/bin/env python3
"""F2 — gate de promotion à DEUX conditions (L3, mémo diag smoke 0714).

Leçon du smoke 0714 : un candidat peut monter la CONVERSION (conv_self ↑) tout en
RÉGRESSANT en généraliste (−45 elo) — il désapprend plus qu'il n'apprend. Promouvoir sur
conv_self seul est un piège. **Règle gravée** : un tour n'est promu champion(t) que si
  (1) PILOTE   : conv_self(cand) ≥ conv_self(champion) + min_delta   (la conversion progresse), ET
  (2) GARDE    : généraliste(cand vs champion) NON-RÉGRESSIF hors-IC  (borne haute IC ≥ 0.5).
La conversion pilote, le généraliste garde. Le cand du smoke (conv↑ mais rate 0.436, hi 0.464<0.5)
aurait été REJETÉ — exactement le but. À appeler par le runner de chaîne L3 à chaque tour.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def decide(conv_cand, conv_champ, gate_rate, gate_n,
           min_delta=0.03, nmin=400):
    """Retourne (promote: bool, reason: str, detail: dict)."""
    if gate_n < nmin:
        return (False, f"INCONCLUANT gate n={gate_n} < {nmin}", {"gate_n": gate_n})
    se = 0.5 / math.sqrt(gate_n)
    lo, hi = gate_rate - 1.96 * se, gate_rate + 1.96 * se
    elo = -400 * math.log10(1 / gate_rate - 1) if 0 < gate_rate < 1 else 0.0
    conv_ok = (conv_cand is not None and conv_champ is not None
               and conv_cand >= conv_champ + min_delta)
    # non-régressif hors-IC = le cand n'est PAS significativement pire (borne haute ≥ 0.5)
    guard_ok = hi >= 0.5
    promote = conv_ok and guard_ok
    detail = {"conv_cand": conv_cand, "conv_champ": conv_champ,
              "conv_delta": None if (conv_cand is None or conv_champ is None) else round(conv_cand - conv_champ, 4),
              "gate_rate": round(gate_rate, 4), "gate_ic": [round(lo, 3), round(hi, 3)],
              "gate_elo": round(elo), "pilote_ok": conv_ok, "garde_ok": guard_ok}
    if promote:
        reason = "PROMU : conversion ↑ ET généraliste non-régressif"
    elif not conv_ok:
        reason = f"REJETÉ : conversion n'avance pas (Δ={detail['conv_delta']} < {min_delta})"
    elif not guard_ok:
        reason = f"REJETÉ : garde généraliste — régresse hors-IC (hi={hi:.3f} < 0.5, elo~{elo:+.0f})"
    else:
        reason = "REJETÉ"
    return (promote, reason, detail)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", help="JSON avec conv_self_cand/conv_self_champ(ou _bootstrap)/gate_rate/gate_n")
    ap.add_argument("--conv-cand", type=float, default=None)
    ap.add_argument("--conv-champ", type=float, default=None)
    ap.add_argument("--gate-rate", type=float, default=None)
    ap.add_argument("--gate-n", type=int, default=None)
    ap.add_argument("--min-delta", type=float, default=0.03)
    ap.add_argument("--nmin", type=int, default=400)
    a = ap.parse_args(argv)

    cc, cp, gr, gn = a.conv_cand, a.conv_champ, a.gate_rate, a.gate_n
    if a.manifest:
        m = json.loads(Path(a.manifest).read_text())
        cc = m.get("conv_self_cand", cc)
        cp = m.get("conv_self_champ", m.get("conv_self_bootstrap", cp))
        gr = m.get("gate_rate", gr)
        gn = m.get("gate_n", gn)
    if None in (cc, cp, gr, gn):
        print("ABORT: entrées manquantes (conv_cand/conv_champ/gate_rate/gate_n)", file=sys.stderr)
        return 2
    promote, reason, detail = decide(cc, cp, gr, gn, a.min_delta, a.nmin)
    out = {"promote": promote, "reason": reason, **detail}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if promote else 1


if __name__ == "__main__":
    sys.exit(main())
