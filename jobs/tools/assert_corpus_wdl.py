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
HEADER_BYTES = 8
SCAN_RECORDS = 1 << 16


DEFAULT_MIN_DRAW_SHARE = 0.10
DEFAULT_MAX_DRAW_SHARE = 0.60
DEFAULT_MAX_SIDE_SKEW = 0.10


def evaluate(counts: dict[int, int],
             min_draw_share: float = DEFAULT_MIN_DRAW_SHARE,
             max_draw_share: float = DEFAULT_MAX_DRAW_SHARE,
             max_side_skew: float = DEFAULT_MAX_SIDE_SKEW) -> dict:
    """Juge un histogramme d'issues. Partagé avec `selfplay_frontier.py merge`,
    pour que la garde soit la MÊME au point de passage et en ligne de commande."""
    n = sum(counts.values())
    if n == 0:
        raise ValueError("zéro record — échec, pas un corpus vide neutre")
    share = {k: counts.get(k, 0) / n for k in (-1, 0, 1)}
    skew = abs(share[1] - share[-1])
    problems = []
    if share[0] < min_draw_share:
        problems.append(
            f"part de nulles {share[0]:.4f} sous le plancher {min_draw_share} — "
            "signature du défaut de racine nulle (corpus cassé mesuré à 0,048)"
        )
    if share[0] > max_draw_share:
        problems.append(
            f"part de nulles {share[0]:.4f} au-dessus du plafond {max_draw_share}"
        )
    if skew > max_side_skew:
        problems.append(
            f"déséquilibre victoires/défaites {skew:.4f} au-dessus de "
            f"{max_side_skew} — le self-play devrait être symétrique"
        )
    return {
        "records": n,
        "counts": {"loss": counts.get(-1, 0), "draw": counts.get(0, 0),
                   "win": counts.get(1, 0)},
        "shares": {"loss": round(share[-1], 6), "draw": round(share[0], 6),
                   "win": round(share[1], 6)},
        "side_skew": round(skew, 6),
        "thresholds": {"min_draw_share": min_draw_share,
                       "max_draw_share": max_draw_share,
                       "max_side_skew": max_side_skew},
        "ok": not problems,
        "problems": problems,
    }


def histogram_from_records(records) -> dict[int, int]:
    """Histogramme depuis des records bruts en mémoire (chemin `merge`)."""
    counts = collections.Counter()
    for rec in records:
        counts[struct.unpack_from("<b", rec, WDL_OFFSET)[0]] += 1
    unexpected = set(counts) - {-1, 0, 1}
    if unexpected:
        raise ValueError(f"étiquettes WDL hors domaine {sorted(unexpected)}")
    return dict(counts)


def histogram(path: Path) -> tuple[int, dict[int, int]]:
    """Compte les issues d'un `.jnnw` sans matérialiser le corpus.

    Les sources de replay peuvent dépasser le gigaoctet. Le canari doit donc
    garder une empreinte mémoire bornée au lieu d'appeler ``Path.read_bytes``.
    """
    size = path.stat().st_size
    if size < HEADER_BYTES:
        raise SystemExit(f"{path}: fichier trop court pour un en-tête jnnw")
    with path.open("rb") as stream:
        header = stream.read(HEADER_BYTES)
        if header[:COUNT_OFFSET] != b"JNNW":
            raise SystemExit(f"{path}: magie jnnw invalide")
        count = struct.unpack_from("<I", header, COUNT_OFFSET)[0]
        if count == 0:
            raise SystemExit(f"{path}: zéro record — échec, pas un corpus vide neutre")
        expected_size = HEADER_BYTES + count * RECORD_BYTES
        if size != expected_size:
            raise SystemExit(
                f"{path}: taille incohérente — {size} octets pour {count} records "
                f"de {RECORD_BYTES} (attendu {expected_size})"
            )
        counts = collections.Counter()
        remaining = count
        while remaining:
            batch_records = min(remaining, SCAN_RECORDS)
            block = stream.read(batch_records * RECORD_BYTES)
            if len(block) != batch_records * RECORD_BYTES:
                raise SystemExit(f"{path}: corpus tronqué pendant le scan WDL")
            for offset in range(WDL_OFFSET, len(block), RECORD_BYTES):
                counts[struct.unpack_from("<b", block, offset)[0]] += 1
            remaining -= batch_records
    unexpected = set(counts) - {-1, 0, 1}
    if unexpected:
        raise SystemExit(f"{path}: étiquettes WDL hors domaine {sorted(unexpected)}")
    return count, dict(counts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, type=Path, help="corpus .jnnw")
    p.add_argument("--min-draw-share", type=float, default=DEFAULT_MIN_DRAW_SHARE,
                   help="plancher de nulles (défaut 0,10 ; cassé=0,048 réparé=0,203)")
    p.add_argument("--max-draw-share", type=float, default=DEFAULT_MAX_DRAW_SHARE,
                   help="plafond de nulles — un corpus qui ne décide jamais "
                        "n'apprend rien non plus")
    p.add_argument("--max-side-skew", type=float, default=DEFAULT_MAX_SIDE_SKEW,
                   help="écart max toléré entre part de victoires et de défaites ; "
                        "le self-play est symétrique, un déséquilibre signale un "
                        "biais de couleur ou d'adjudication")
    p.add_argument("--out", type=Path, help="où écrire le rapport JSON")
    args = p.parse_args(argv)

    _, counts = histogram(args.data)
    try:
        report = evaluate(counts, args.min_draw_share, args.max_draw_share,
                          args.max_side_skew)
    except ValueError as exc:
        raise SystemExit(f"{args.data}: {exc}")
    problems = report["problems"]
    report = {"schema": 1, "data": str(args.data), **report}
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    for problem in problems:
        print(f"CORPUS_WDL_ABORT: {problem}", file=sys.stderr)
    return 6 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
