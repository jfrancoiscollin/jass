#!/usr/bin/env python3
"""B1 — chiffrage de l'ARBITRE-d14-AU-CAP (le gate AVANT intégration, mémo L3).

Le mémo impose : avant de remplacer le label ply-cap menteur (~19 %) par un oracle de
recherche (deep-relabel d14+egdb), CHIFFRER le surcoût = plycap_rate × coût_d14 et vérifier
qu'il tient sous le seuil (JFC : ≤ +25 % wall-clock/tour). Cet instrument mesure, sur un lot
témoin de self-play champion (config gen standard : d10, cap MAXPLIES) :
  - plycap_rate = fraction de parties qui atteignent le ply-cap (r.reason == "ply cap") ;
  - coût/partie (CPU) de la gen ;
  - et COLLECTE les positions FINALES cappées (r.fens[-1]) dans un JNNW → le job les passe
    à `jass --deep-relabel 14 --egdb` (coût_d14 + taux de désaccord vs nulle = le mensonge).

Réutilise ``calibrate_vs_scan.play_game`` (adjud-OFF ; le cap → GameResult('D','ply cap'))
et ``scan_selfplay_gen.fen_to_record``. Sharding par index de partie (--shard/--nshards).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_vs_scan as cv
from scan_selfplay_gen import fen_to_record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jass", required=True)
    ap.add_argument("--pattern", required=True, help="champion pilote (gen2-mmto)")
    ap.add_argument("--openings-file", default=None)
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--max-plies", type=int, default=200)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--caps-out", required=True, help="JNNW des positions finales cappées")
    ap.add_argument("--out", required=True, help="JSON de chiffrage")
    a = ap.parse_args(argv)

    if a.openings_file:
        openings = [o for o in (ln.split("#", 1)[0].strip()
                    for ln in open(a.openings_file)) if o]
    else:
        openings = ["B:W28,31-50:B1-20", "B:W31,32,34-50:B1-20"]
    if not openings:
        sys.exit("ABORT: aucune ouverture")

    champ = cv.JassEngine(a.jass, pattern_path=a.pattern)
    referee = cv.Referee(a.jass)
    n_games = n_exhaust = 0
    play_sec = 0.0
    caps = bytearray()
    reasons = {}
    # « épuisement » = nulle SANS terminal réel : la position gagnée n'a pas été convertie à temps
    # (ply cap 200 OU règle 25-coups no-progress). C'est le mensonge que l'arbitre-d14 corrige.
    EXHAUST = ("ply cap", "25-move rule")
    for g in range(a.games):
        if g % a.nshards != a.shard:
            continue
        opening = openings[g % len(openings)]
        t0 = time.time()
        try:
            r = cv.play_game(champ, champ, referee, opening,
                             depth=a.depth, max_plies=a.max_plies)
        except Exception as exc:  # noqa: BLE001
            print(f"  game {g}: {exc}", file=sys.stderr)
            continue
        play_sec += time.time() - t0
        n_games += 1
        reason = getattr(r, "reason", "") or ""
        key = "25-move" if reason.startswith("25-move") else ("ply-cap" if reason.startswith("ply cap")
              else ("no-legal" if reason.startswith("no legal") else "other"))
        reasons[key] = reasons.get(key, 0) + 1
        if reason in EXHAUST and getattr(r, "outcome", "") == "D" and r.fens:
            n_exhaust += 1
            caps += fen_to_record(r.fens[-1], 0)   # wdl=0 placeholder (deep-relabel le remplira)
    champ.close(); referee.close()

    Path(a.caps_out).write_bytes(b"JNNW" + struct.pack("<I", n_exhaust) + bytes(caps))
    res = {
        "n_games": n_games, "n_cap": n_exhaust,   # n_cap = nulles d'épuisement (ply-cap + 25-move)
        "plycap_rate": None if n_games == 0 else round(n_exhaust / n_games, 4),
        "reasons": reasons,
        "play_sec": round(play_sec, 3),
        "sec_per_game": None if n_games == 0 else round(play_sec / n_games, 4),
        "depth": a.depth, "max_plies": a.max_plies,
    }
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
