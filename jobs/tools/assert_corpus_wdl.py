#!/usr/bin/env python3
"""Refuse un corpus WDL dont la distribution d'issues est aberrante.

Pourquoi cet outil existe. Du 24 au 27 juillet 2026, trois corpus L3-PURE
(`home-0944` M1, `home-0966bis` M2, et par héritage TURNOVER) ont été générés
par un moteur dont `search()` renvoyait un coup NUL sur toute racine répétée.
En self-play `--gen-data-wdl`, `apply_move` rejette ce coup nul, la boucle de
jeu casse, `hit_ply_cap` reste vrai et `--drop-plycap` **jette la partie
entière**. Comme les répétitions arrivent dans les positions de manœuvre, ce
sont précisément les nulles qui disparaissaient.

Mesuré sur le binaire d'avant et d'après le correctif `9c1d1e8e`, mêmes graine,
parent, profondeur et options (3000 records, d8, `--drop-plycap`) :

    moteur cassé  : 47,8 % L / **4,8 % N** / 47,4 % W
    moteur réparé : 39,5 % L / **20,3 % N** / 40,2 % W

Un facteur 4,2 sur les nulles, invisible dans tous les compteurs que les jobs
publiaient à l'époque. Aucune garde de l'époque ne pouvait le voir : elles
portaient toutes sur le CODE (`grep root_is_drawn`), jamais sur les DONNÉES.
Celle-ci porte sur les données, donc elle attrape aussi la prochaine cause,
inconnue, qui produirait le même symptôme.

Sortie : un JSON avec l'histogramme, et un code retour non nul si le corpus
sort de la bande.
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

RECORD_BYTES = 38   # 32 bitboards + 1 stm + 4 score + 1 wdl
WDL_OFFSET = 37
COUNT_OFFSET = 4


def histogram(path: Path) -> tuple[int, dict[int, int]]:
    """Compte les issues d'un `.jnnw`. Le nombre de records est dans l'en-tête."""
    blob = path.read_bytes()
    if len(blob) < COUNT_OFFSET + 4:
        raise SystemExit(f"{path}: fichier trop court pour un en-tête jnnw")
    count = struct.unpack_from("<I", blob, COUNT_OFFSET)[0]
    if count == 0:
        raise SystemExit(f"{path}: zéro record — échec, pas un corpus vide neutre")
    header = len(blob) - count * RECORD_BYTES
    if header < 0 or (len(blob) - header) % RECORD_BYTES:
        raise SystemExit(
            f"{path}: taille incohérente — {len(blob)} octets pour {count} records "
            f"de {RECORD_BYTES}"
        )
    counts = collections.Counter()
    for i in range(count):
        counts[struct.unpack_from("<b", blob, header + i * RECORD_BYTES + WDL_OFFSET)[0]] += 1
    unexpected = set(counts) - {-1, 0, 1}
    if unexpected:
        raise SystemExit(f"{path}: étiquettes WDL hors domaine {sorted(unexpected)}")
    return count, dict(counts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, type=Path, help="corpus .jnnw")
    p.add_argument("--min-draw-share", type=float, default=0.10,
                   help="plancher de nulles (défaut 0,10 ; cassé=0,048 réparé=0,203)")
    p.add_argument("--max-draw-share", type=float, default=0.60,
                   help="plafond de nulles — un corpus qui ne décide jamais "
                        "n'apprend rien non plus")
    p.add_argument("--max-side-skew", type=float, default=0.10,
                   help="écart max toléré entre part de victoires et de défaites ; "
                        "le self-play est symétrique, un déséquilibre signale un "
                        "biais de couleur ou d'adjudication")
    p.add_argument("--out", type=Path, help="où écrire le rapport JSON")
    args = p.parse_args(argv)

    n, counts = histogram(args.data)
    share = {k: counts.get(k, 0) / n for k in (-1, 0, 1)}
    skew = abs(share[1] - share[-1])

    problems = []
    if share[0] < args.min_draw_share:
        problems.append(
            f"part de nulles {share[0]:.4f} sous le plancher {args.min_draw_share} — "
            "signature du défaut de racine nulle (corpus cassé mesuré à 0,048)"
        )
    if share[0] > args.max_draw_share:
        problems.append(
            f"part de nulles {share[0]:.4f} au-dessus du plafond {args.max_draw_share}"
        )
    if skew > args.max_side_skew:
        problems.append(
            f"déséquilibre victoires/défaites {skew:.4f} au-dessus de "
            f"{args.max_side_skew} — le self-play devrait être symétrique"
        )

    report = {
        "schema": 1,
        "data": str(args.data),
        "records": n,
        "counts": {"loss": counts.get(-1, 0), "draw": counts.get(0, 0),
                   "win": counts.get(1, 0)},
        "shares": {"loss": round(share[-1], 6), "draw": round(share[0], 6),
                   "win": round(share[1], 6)},
        "side_skew": round(skew, 6),
        "thresholds": {"min_draw_share": args.min_draw_share,
                       "max_draw_share": args.max_draw_share,
                       "max_side_skew": args.max_side_skew},
        "ok": not problems,
        "problems": problems,
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    for problem in problems:
        print(f"CORPUS_WDL_ABORT: {problem}", file=sys.stderr)
    return 6 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
