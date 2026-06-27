#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# master_games_to_jnnw.py — briefing externe #6 : « parties de maîtres comme
# DISTRIBUTION » (PAS des racines de combos sur-pondérées, ce qui a corrompu les
# poids matériels en 0464/0466/0468).
#
# Prend des parties ENTIÈRES (expert_games.db : vraies parties lidraughts/maîtres),
# échantillonne les positions QUIÈTES, étiquette par le RÉSULTAT RÉEL (W/D/L,
# STM-POV) et écrit un JNNW à FRÉQUENCE NATURELLE (aucun oversampling). Les
# positions quiètes de joueurs FORTS discriminent la shot-vulnérabilité d'une
# façon que le self-play faible ne peut pas — sans injecter de moteur dans le
# label (ni distillation, ni auto-supervision).
#
# Filtre quiet (gratuit, exact) : en dames internationales la capture est
# OBLIGATOIRE, donc une position est quiète SSI le coup joué depuis elle n'est
# PAS une capture (notation PDN : 'x' = capture, '-' = coup simple). Pas besoin
# d'un générateur de coups séparé.
#
# Sortie = JNNW standard (magic 'JNNW' + uint32 count + records 38o), à MÉLANGER
# au pool d'entraînement à fréquence naturelle (pas de réplication).
#
# Usage:
#   tools/master_games_to_jnnw.py --db data/expert_games.db --jass ./build/jass \
#       --out masters.jnnw [--include-draws] [--min-plies 24] [--skip-open 8] \
#       [--skip-endgame-pieces 8] [--max-games N] [--shard K --nshards M]
import argparse
import logging
import os
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdn_to_jnnw import (  # noqa: E402
    JassOracle, extract_moves, fen_to_bitboards, wdl_from_stm_pov,
    _strip_tags_and_comments, _REC_STRUCT,
)

JNNW_MAGIC = b"JNNW"


def _popcount(x: int) -> int:
    return bin(x).count("1")


def _piece_count(wm: int, wk: int, bm: int, bk: int) -> int:
    return _popcount(wm) + _popcount(wk) + _popcount(bm) + _popcount(bk)


def is_capture(move: str) -> bool:
    """A PDN move token is a capture iff it contains 'x' (FMJD majority rule
    makes captures mandatory → a non-capture move means NO capture was
    available → the position is quiet)."""
    return "x" in move


def emit_game(oracle: JassOracle, body_out: bytearray, pdn: str, result: str,
              *, min_plies: int, skip_open: int, skip_endgame_pieces: int,
              log: logging.Logger) -> int:
    """Append quiet positions of one game to `body_out`. Returns #records.
    Labels = real result (STM-POV). Natural frequency (every quiet position
    once). A game that fails to replay contributes 0 (already-appended records
    of THIS game are rolled back)."""
    moves = extract_moves(_strip_tags_and_comments(pdn or ""))
    if len(moves) < min_plies:
        return 0
    mark = len(body_out)
    try:
        oracle.reset()
        for ply, mv in enumerate(moves):
            # position BEFORE the move `mv` is played
            if ply >= skip_open and not is_capture(mv):
                fen = oracle.fen()
                stm, wm, wk, bm, bk = fen_to_bitboards(fen)
                if _piece_count(wm, wk, bm, bk) >= skip_endgame_pieces:
                    wdl = wdl_from_stm_pov(result, stm)
                    body_out += _REC_STRUCT.pack(wm, wk, bm, bk, stm, 0, wdl)
            if not oracle.apply(mv):
                # malformed/illegal move : roll back this game, skip it
                del body_out[mark:]
                return 0
    except Exception as exc:  # noqa: BLE001
        log.warning("game skipped (%s)", exc)
        del body_out[mark:]
        return 0
    return (len(body_out) - mark) // _REC_STRUCT.size


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="sqlite expert_games.db")
    ap.add_argument("--jass", required=True, help="jass binary (HUB oracle)")
    ap.add_argument("--out", required=True, help="output .jnnw")
    ap.add_argument("--include-draws", action="store_true",
                    help="also emit drawn games (wdl=0). Default: decisive only.")
    ap.add_argument("--min-plies", type=int, default=24,
                    help="skip games shorter than this (default 24)")
    ap.add_argument("--skip-open", type=int, default=8,
                    help="skip the first N plies (generic openings ; default 8)")
    ap.add_argument("--skip-endgame-pieces", type=int, default=8,
                    help="only emit positions with >= this many pieces (keep the "
                         "MIDDLEGAME where the gap is ; default 8 = exclude <=7p egdb zone)")
    ap.add_argument("--max-games", type=int, default=0, help="0 = all")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    log = logging.getLogger("masters")

    results = ("1-0", "0-1") if not args.include_draws else ("1-0", "0-1", "1/2-1/2")
    placeholders = ",".join("?" for _ in results)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    q = (f"SELECT id,pdn,result FROM expert_games "
         f"WHERE result IN ({placeholders}) AND num_plies >= ? ORDER BY id")
    rows = conn.execute(q, (*results, args.min_plies))

    oracle = JassOracle(Path(args.jass), log)
    body = bytearray()
    ngames = nrec = nseen = 0
    try:
        for gid, pdn, result in rows:
            if (nseen % args.nshards) != args.shard:
                nseen += 1
                continue
            nseen += 1
            if args.max_games and ngames >= args.max_games:
                break
            r = emit_game(oracle, body, pdn, result,
                          min_plies=args.min_plies, skip_open=args.skip_open,
                          skip_endgame_pieces=args.skip_endgame_pieces, log=log)
            if r:
                ngames += 1
                nrec += r
    finally:
        oracle.close()

    n = len(body) // _REC_STRUCT.size
    with open(args.out, "wb") as f:
        f.write(JNNW_MAGIC + struct.pack("<I", n))
        f.write(body)
    # WDL balance report (a master corpus is loss-biased for the weaker-styled
    # openings ; the fit may want reweighting — report it so the caller decides).
    w = d = l = 0
    for i in range(n):
        off = i * _REC_STRUCT.size
        wdl = struct.unpack_from("<b", body, off + 37)[0]
        w += wdl > 0
        l += wdl < 0
        d += wdl == 0
    print(f"masters→jnnw : games={ngames} positions={n} (W={w} D={d} L={l}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
