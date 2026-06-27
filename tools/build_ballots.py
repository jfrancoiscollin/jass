#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# build_ballots.py — briefing externe #2 : remplacer `--random-open-plies`
# (ouvertures équilibrées génériques) par un BALLOT de vraies structures
# d'ouverture, DIVERSES et éventuellement DÉSÉQUILIBRÉES (= la distribution du
# set 0440), jouées dans les DEUX couleurs.
#
# Extrait les positions à un nombre de plis donné (défaut 6-12) depuis
# expert_games.db, dédoublonne, et (par défaut) ajoute le MIROIR couleur de
# chaque position (rotation 180° + échange des couleurs : symétrie exacte des
# dames) pour que le ballot soit joué des deux côtés. Sortie = JNNW utilisable
# tel quel comme `--seed-file` (avec `--seed-frac 100` pour démarrer CHAQUE
# partie d'un ballot). Les champs score/wdl sont nuls (un seed n'est qu'une
# position de départ).
#
# Usage:
#   tools/build_ballots.py --db data/expert_games.db --jass ./build/jass \
#       --out ballots.jnnw [--ply-lo 6 --ply-hi 12] [--min-imbalance 0] \
#       [--no-mirror] [--max-games N] [--cap 600]
import argparse
import logging
import os
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdn_to_jnnw import (  # noqa: E402
    JassOracle, extract_moves, fen_to_bitboards, _strip_tags_and_comments,
    _REC_STRUCT,
)

JNNW_MAGIC = b"JNNW"


def mirror50(bb: int) -> int:
    """Reverse the low 50 bits: square s (1..50) -> square 51-s, i.e. bit i ->
    bit 49-i. This is the draughts 180° board rotation."""
    r = 0
    for i in range(50):
        if (bb >> i) & 1:
            r |= 1 << (49 - i)
    return r


def color_swap_mirror(wm: int, wk: int, bm: int, bk: int, stm: int):
    """180° rotation + colour swap = exact draughts symmetry. Returns a
    strategically-identical position with the side-to-move flipped, so a ballot
    played from it exercises the OTHER colour."""
    return (mirror50(bm), mirror50(bk), mirror50(wm), mirror50(wk), 1 - stm)


def _popcount(x: int) -> int:
    return bin(x).count("1")


def material_imbalance(wm, wk, bm, bk) -> int:
    """|white men+3·kings − black men+3·kings| (men=1, king=3)."""
    return abs((_popcount(wm) + 3 * _popcount(wk)) - (_popcount(bm) + 3 * _popcount(bk)))


def collect_game(oracle: JassOracle, pdn: str, *, ply_lo: int, ply_hi: int,
                 min_imbalance: int, log: logging.Logger):
    """Yield (wm,wk,bm,bk,stm) for the position at each ply in [ply_lo, ply_hi].
    A game that fails to replay yields nothing."""
    moves = extract_moves(_strip_tags_and_comments(pdn or ""))
    if len(moves) <= ply_lo:
        return []
    out = []
    try:
        oracle.reset()
        for ply, mv in enumerate(moves):
            if ply_lo <= ply <= ply_hi:
                stm, wm, wk, bm, bk = fen_to_bitboards(oracle.fen())
                if material_imbalance(wm, wk, bm, bk) >= min_imbalance:
                    out.append((wm, wk, bm, bk, stm))
            if ply > ply_hi:
                break
            if not oracle.apply(mv):
                return []
    except Exception as exc:  # noqa: BLE001
        log.warning("game skipped (%s)", exc)
        return []
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--jass", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ply-lo", type=int, default=6)
    ap.add_argument("--ply-hi", type=int, default=12)
    ap.add_argument("--min-imbalance", type=int, default=0,
                    help="require |material diff| >= this (0 = all, for diversity ; "
                         "1+ = only sharp/down-a-pawn structures)")
    ap.add_argument("--no-mirror", action="store_true",
                    help="do NOT add the colour-mirror of each ballot (default: add it)")
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--cap", type=int, default=0, help="0 = no cap on #unique ballots")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    log = logging.getLogger("ballots")

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = conn.execute("SELECT pdn FROM expert_games ORDER BY id")

    oracle = JassOracle(Path(args.jass), log)
    seen: set[tuple] = set()
    body = bytearray()
    ngames = 0
    try:
        for (pdn,) in rows:
            if args.max_games and ngames >= args.max_games:
                break
            ngames += 1
            for pos in collect_game(oracle, pdn, ply_lo=args.ply_lo,
                                    ply_hi=args.ply_hi, min_imbalance=args.min_imbalance,
                                    log=log):
                variants = [pos]
                if not args.no_mirror:
                    variants.append(color_swap_mirror(*pos))
                for (wm, wk, bm, bk, stm) in variants:
                    key = (wm, wk, bm, bk, stm)
                    if key in seen:
                        continue
                    seen.add(key)
                    body += _REC_STRUCT.pack(wm, wk, bm, bk, stm, 0, 0)
                    if args.cap and len(seen) >= args.cap:
                        break
                if args.cap and len(seen) >= args.cap:
                    break
            if args.cap and len(seen) >= args.cap:
                break
    finally:
        oracle.close()

    n = len(body) // _REC_STRUCT.size
    with open(args.out, "wb") as f:
        f.write(JNNW_MAGIC + struct.pack("<I", n))
        f.write(body)
    print(f"ballots : games={ngames} unique-positions={n} "
          f"(ply {args.ply_lo}-{args.ply_hi}, imbalance>={args.min_imbalance}, "
          f"mirror={'no' if args.no_mirror else 'yes'}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
