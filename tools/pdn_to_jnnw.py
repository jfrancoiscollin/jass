#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Convert master-game PDNs stored in `data/expert_games.db` into a
single JNNW record stream consumable by `tools/train_v3.py`.

Pipeline position (Cycle 8 of the dilf / Lidraughts roadmap)
------------------------------------------------------------
    Lidraughts API
        │  (tools/fetch_lidraughts_games.py)
        ▼
    data/expert_games.db   (SQLite, one row per game, PDN as TEXT)
        │  (this script)
        ▼
    master.jnnw            (38 B / record, magic "JNNW")
        │  (tools/train_v3.py --master-data)
        ▼
    NNUE trained on master + self-play blended labels

Design — why we delegate position state to jass
-----------------------------------------------
International-draughts movegen is non-trivial (mandatory longest
capture chain, king ray captures, "soufflage" semantics).  Re-
implementing it in Python would be a fresh bug surface; instead we
spawn one long-lived `./build/jass` HUB-mode subprocess and feed it
the PDN moves via `apply <m>`.  Jass's `parse_move` already accepts
the multi-jump capture notation Lidraughts produces (e.g.
`32x14x3` — it keys on the first and last squares and resolves the
captured-piece set from the legal-move list), so we don't have to
parse capture trajectories ourselves.

Subprocess overhead: ~0.1-0.5 ms per HUB round-trip on Unix pipes.
Per game: ~80 plies × (apply + fen) = ~160 round-trips ≈ 16-80 ms.
For 200 K games: ~1-5 h wall time on a single CCX23 core.  Acceptable
for a one-shot batch; if we ever need it faster, the right move is
to add a native `--pdn-to-jnnw` mode to `jass` that loops in C++.

JNNW per-record layout (cf. src/main.cpp:216)
---------------------------------------------
    32 B   uint64×4 bitboards (white_men, white_kings, black_men, black_kings)
     1 B   uint8    stm       (0 = white to move, 1 = black to move)
     4 B   int32    score     (centipawn, STM POV — we write 0 for master
                                records since there's no per-position search;
                                the score-MSE loss term should be down-weighted
                                or masked on master data by the trainer)
     1 B   int8     wdl       (+1 / 0 / -1, STM POV of the game's outcome
                                at sample time)

File header: 4 B magic "JNNW" + 4 B uint32 count.

CLI
---
    python3 tools/pdn_to_jnnw.py                            \\
        --db   data/expert_games.db                         \\
        --out  master.jnnw                                  \\
        --min-rating 1600                                   \\
        --variant standard                                  \\
        --min-plies 20                                      \\
        --jass ./build/jass
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# JNNW format constants (kept in sync with src/main.cpp:216 and
# tools/scout_wdl.py:60).
# ---------------------------------------------------------------------------

JNNW_MAGIC      = b"JNNW"
JNNW_HEADER_SZ  = 8
JNNW_RECORD_SZ  = 38   # 32 + 1 + 4 + 1
# struct format: 4 uint64 (bitboards) + 1 uint8 stm + 1 int32 score + 1 int8 wdl
_REC_STRUCT     = struct.Struct("<QQQQBib")
assert _REC_STRUCT.size == JNNW_RECORD_SZ


# ---------------------------------------------------------------------------
# PDN tokenisation
# ---------------------------------------------------------------------------

_MOVENO_RE  = re.compile(r'^\d+\.+$')
_RESULT_RE  = re.compile(r'^(1-0|0-1|1/2-1/2|2-0|0-2|1-1|½-½|\*)$')
# Move token: at least one '-' or 'x' between digits, optionally a chain
# (e.g. 32-28, 28x19, 32x14x3).  Square numbers 1-50.
_MOVE_RE    = re.compile(r'^\d{1,2}([-x]\d{1,2})+$')


def extract_moves(pdn_body: str) -> list[str]:
    """Return the main-line move tokens in order.  Comments {…} and
    variations (…) are dropped; move numbers and result tokens are
    skipped."""
    s = pdn_body
    # Strip {…} comments (possibly nested? PDN spec says no, but be lenient).
    s = re.sub(r'\{[^}]*\}', ' ', s)
    # Strip (…) variations.  Iterate to handle simple nesting.
    while '(' in s:
        before = s
        s = re.sub(r'\([^()]*\)', ' ', s)
        if s == before:
            # unbalanced parens — drop the rest defensively
            s = s.split('(', 1)[0]
            break

    moves: list[str] = []
    for tok in s.split():
        if _MOVENO_RE.match(tok) or _RESULT_RE.match(tok):
            continue
        if _MOVE_RE.match(tok):
            moves.append(tok)
    return moves


# ---------------------------------------------------------------------------
# FEN → bitboards
# ---------------------------------------------------------------------------

def fen_to_bitboards(fen: str) -> tuple[int, int, int, int, int]:
    """Parse a Hub-style FEN (`W:Wlist:Blist`) into
    `(stm, white_men, white_kings, black_men, black_kings)`.

    stm is 0 for white-to-move, 1 for black-to-move.  Each *_bb is a
    50-bit integer with bit `i` set when piece is on square `i+1`,
    matching `square_to_bit` in `src/types.hpp`.
    """
    parts = fen.split(':')
    if len(parts) != 3:
        raise ValueError(f"FEN: expected 3 colon-separated parts, got {fen!r}")

    stm_tok = parts[0].strip()
    if stm_tok not in ('W', 'B'):
        raise ValueError(f"FEN: bad STM token {stm_tok!r}")
    stm = 0 if stm_tok == 'W' else 1

    wp = parts[1].strip()
    bp = parts[2].strip()
    if not wp.startswith('W') or not bp.startswith('B'):
        raise ValueError(f"FEN: expected W… / B… piece lists, got {fen!r}")

    wm, wk = _parse_piece_list(wp[1:])
    bm, bk = _parse_piece_list(bp[1:])
    return stm, wm, wk, bm, bk


def _parse_piece_list(s: str) -> tuple[int, int]:
    """Parse "31,32,K45,46-50" into `(men_bb, kings_bb)`."""
    men = 0
    kings = 0
    for raw in s.split(','):
        tok = raw.strip()
        if not tok:
            continue
        is_king = False
        if tok[0] in ('K', 'k'):
            is_king = True
            tok = tok[1:]
        if '-' in tok:
            a, b = tok.split('-', 1)
            first, last = int(a), int(b)
            if first < 1 or last > 50 or first > last:
                raise ValueError(f"FEN piece list bad range {raw!r}")
            for sq in range(first, last + 1):
                bit = 1 << (sq - 1)
                if is_king:
                    kings |= bit
                else:
                    men |= bit
        else:
            sq = int(tok)
            if sq < 1 or sq > 50:
                raise ValueError(f"FEN piece list bad square {raw!r}")
            bit = 1 << (sq - 1)
            if is_king:
                kings |= bit
            else:
                men |= bit
    return men, kings


# ---------------------------------------------------------------------------
# jass HUB subprocess oracle
# ---------------------------------------------------------------------------

class JassOracle:
    """Wraps a long-lived `jass` HUB process for position simulation.

    Lifecycle: create once, reset()/apply()/fen() many times, close() at end.
    """

    def __init__(self, jass_path: Path, log: logging.Logger):
        self.log = log
        # `--no-book` so opening-book look-ups don't interfere with `apply`.
        # `--no-nnue` because we don't search, only update position; saves
        # the NNUE load time on startup.
        self.proc = subprocess.Popen(
            [str(jass_path), "--no-book", "--no-nnue"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def _send(self, cmd: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _read_line(self) -> str:
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("jass: subprocess closed stdout unexpectedly")
        return line.rstrip("\n")

    def reset(self) -> None:
        self._send("position startpos")
        line = self._read_line()
        if not line.startswith("ok"):
            raise RuntimeError(f"reset: expected 'ok', got {line!r}")

    def apply(self, move: str) -> bool:
        self._send(f"apply {move}")
        line = self._read_line()
        return line.startswith("ok")

    def fen(self) -> str:
        self._send("fen")
        line = self._read_line()
        if not line.startswith("fen "):
            raise RuntimeError(f"fen: bad response {line!r}")
        return line[4:].strip()

    def close(self) -> None:
        try:
            self._send("quit")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# ---------------------------------------------------------------------------
# WDL bookkeeping
# ---------------------------------------------------------------------------

def wdl_from_stm_pov(result: str, stm: int) -> int:
    """Map a normalised game result to {+1, 0, -1} from STM's perspective.

    `result` ∈ {'1-0', '0-1', '1/2-1/2'} (white-perspective).
    `stm` is 0 for white-to-move, 1 for black-to-move.
    """
    if result == '1/2-1/2':
        return 0
    white_won = (result == '1-0')
    stm_is_white = (stm == 0)
    return 1 if (white_won == stm_is_white) else -1


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

def emit_record(out_file, wm: int, wk: int, bm: int, bk: int,
                stm: int, score: int, wdl: int) -> None:
    out_file.write(_REC_STRUCT.pack(wm, wk, bm, bk, stm, score, wdl))


def convert_one_game(oracle: JassOracle, out_file, pdn: str, result: str,
                     log: logging.Logger,
                     game_idx: int) -> tuple[int, bool]:
    """Convert one game's PDN into a sequence of JNNW records appended
    to `out_file`.

    Returns (records_written, ok).  `ok` is False when the game was
    rejected (move couldn't be applied, malformed FEN, …); partial
    records for the failed game are NOT written (we buffer first then
    flush only on success).
    """
    body = _strip_tags_and_comments(pdn)
    moves = extract_moves(body)
    if not moves:
        return 0, False

    oracle.reset()

    # We buffer records in memory for this game and only flush them
    # once the whole game has been replayed successfully.  This keeps
    # partially-applied games out of the output when an exotic move
    # token confuses jass.
    buf = bytearray()

    # Record the initial (startpos) position too: it has the same outcome
    # label as every other position in the game.
    fen0 = oracle.fen()
    stm0, wm, wk, bm, bk = fen_to_bitboards(fen0)
    buf.extend(_REC_STRUCT.pack(
        wm, wk, bm, bk, stm0, 0, wdl_from_stm_pov(result, stm0)))

    for i, mv in enumerate(moves):
        if not oracle.apply(mv):
            log.debug("game %d: apply '%s' (move #%d) failed; skipping game",
                      game_idx, mv, i + 1)
            return 0, False
        fen = oracle.fen()
        try:
            stm, wm, wk, bm, bk = fen_to_bitboards(fen)
        except ValueError as exc:
            log.debug("game %d: FEN parse failed at move #%d: %s",
                      game_idx, i + 1, exc)
            return 0, False
        buf.extend(_REC_STRUCT.pack(
            wm, wk, bm, bk, stm, 0, wdl_from_stm_pov(result, stm)))

    out_file.write(buf)
    return len(buf) // JNNW_RECORD_SZ, True


def _strip_tags_and_comments(pdn: str) -> str:
    """Drop [Tag "..."] lines, keep the move-text body."""
    lines = []
    for ln in pdn.splitlines():
        s = ln.strip()
        if not s or s.startswith('['):
            continue
        lines.append(s)
    return " ".join(lines)


# ---------------------------------------------------------------------------
# SQLite read side
# ---------------------------------------------------------------------------

def select_games(conn: sqlite3.Connection, min_rating: int,
                 variant: str, min_plies: int,
                 rating_mode: str = "min"):
    """Yield (id, pdn, result) for each game matching the filters.

    rating_mode controls how the floor applies when the two players
    have different ratings:
      * "min" (strict): both white_rating AND black_rating must be
                        >= min_rating. Used for "pure" subsets where
                        both sides played at the target level.
      * "max" (loose):  it's enough that EITHER player has rating
                        >= min_rating. Used for volume — every game
                        where at least one master-class player took
                        part still carries useful signal.
    """
    if rating_mode not in ("min", "max"):
        raise ValueError(f"rating_mode must be 'min' or 'max', got {rating_mode!r}")
    rating_clause = (
        "MIN(white_rating, black_rating) >= ?"
        if rating_mode == "min"
        else "MAX(white_rating, black_rating) >= ?"
    )
    cur = conn.execute(
        f"""
        SELECT id, pdn, result
        FROM expert_games
        WHERE variant = ?
          AND num_plies >= ?
          AND white_rating IS NOT NULL
          AND black_rating IS NOT NULL
          AND {rating_clause}
          AND result IN ('1-0', '0-1', '1/2-1/2')
        ORDER BY id
        """,
        (variant, min_plies, min_rating),
    )
    for row in cur:
        yield row


# ---------------------------------------------------------------------------
# Header patching: write header placeholder, append records, patch count.
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db", type=Path, required=True,
                   help="SQLite path (data/expert_games.db).")
    p.add_argument("--out", type=Path, required=True,
                   help="Output JNNW file path.")
    p.add_argument("--jass", type=Path, default=Path("./build/jass"),
                   help="Path to the jass binary (used as position oracle).")
    p.add_argument("--min-rating", type=int, default=1600,
                   help="Rating cutoff (see --rating-mode for how it's applied).")
    p.add_argument("--rating-mode", choices=("min", "max"), default="min",
                   help="How the --min-rating cutoff is applied: "
                        "'min' (strict) requires BOTH players >= cutoff; "
                        "'max' (loose) requires at least one to. The strict "
                        "mode produces a smaller 'pure' subset; the loose "
                        "mode matches Draught Master's no-per-game-filter "
                        "behaviour and yields ~5x more records on a typical "
                        "Lidraughts pool.")
    p.add_argument("--variant", default="standard",
                   help="PDN variant tag to keep (others skipped).")
    p.add_argument("--min-plies", type=int, default=20,
                   help="Skip very short games (abandons, joke games).")
    p.add_argument("--max-games", type=int, default=0,
                   help="Cap on number of games processed. 0 = no cap.")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("pdn_to_jnnw")

    if not args.jass.exists():
        log.error("jass binary not found: %s", args.jass)
        return 3
    if not args.db.exists():
        log.error("DB not found: %s", args.db)
        return 3

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_file = args.out.open("wb")
    # Placeholder header — we patch the count at the end.
    out_file.write(JNNW_MAGIC + struct.pack("<I", 0))

    conn = sqlite3.connect(args.db)
    oracle = JassOracle(args.jass, log)

    total_records = 0
    games_ok = 0
    games_skipped = 0
    try:
        for game_idx, (gid, pdn, result) in enumerate(
                select_games(conn, args.min_rating, args.variant,
                             args.min_plies, rating_mode=args.rating_mode)):
            if args.max_games and game_idx >= args.max_games:
                break
            nrec, ok = convert_one_game(oracle, out_file, pdn, result,
                                        log, gid)
            if ok:
                games_ok += 1
                total_records += nrec
            else:
                games_skipped += 1
            if (game_idx + 1) % 1000 == 0:
                log.info("processed %d games | %d ok, %d skipped | "
                         "%d records so far",
                         game_idx + 1, games_ok, games_skipped, total_records)
    finally:
        oracle.close()
        conn.close()

    # Patch the count.
    out_file.seek(4)
    out_file.write(struct.pack("<I", total_records))
    out_file.close()

    log.info("done. %d games OK, %d skipped. %d JNNW records written to %s "
             "(%d bytes).",
             games_ok, games_skipped, total_records, args.out,
             JNNW_HEADER_SZ + total_records * JNNW_RECORD_SZ)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
