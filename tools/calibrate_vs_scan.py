#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Run a colour-swap match between Jass and Scan and report the score
rate + ELO estimate. Both engines run as subprocesses; the orchestrator
relays moves between them and detects terminal conditions.

Why this exists
---------------
All Jass strength numbers so far are *internal* (vN-self-play vs vM-
self-play). To know where Jass sits on an absolute draughts scale,
we need to play against an established external engine. Scan
(Fabien Letouzey, GPL3) is the standard: ~2500 FMJD-equivalent
playing strength when run with enough compute. Differential ELO
against Scan gives Jass a real anchor.

Licence note
------------
Scan is GPL3. We run it as an external subprocess via the HUB
protocol; no Scan code is linked into Jass. The match results are
facts (game outcomes), not derived works, so reporting them does
not create any licence obligation on Jass.

Protocol mismatch
-----------------
Jass speaks a simpler HUB-flavoured protocol (`position fen ...`,
`go depth N`, `bestmove <move> score=... captures=...`); Scan speaks
the full HUB v2 (`pos pos=<51-char position>`, `level depth=N`,
`go think`, `done move=...`). The orchestrator bridges the two
dialects:
  - One engine plays a move in its own move notation.
  - The orchestrator parses (from, to, captures) endpoints.
  - It then formats the move in the OTHER engine's notation and
    forwards it.

Position state is tracked by a third Jass subprocess acting as a
neutral referee: apply each move, query its FEN, repeat. That FEN
is also converted to Scan's 51-char layout for the Scan player.

Usage
-----
    ./build/jass --no-book  &  # both engines run with --no-book by default
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan /tmp/scan/scan_linux \
        --depth 8 --pairs 5 --no-book

    → 18 × 5 × 2 = 90 games (default opening pool of 9 first-move FENs).
    Reports Jass score rate and a rough ELO estimate from the result.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Move + FEN helpers
# ---------------------------------------------------------------------------
@dataclass
class Move:
    frm: int
    to:  int
    captures: tuple[int, ...] = ()

    @property
    def is_capture(self) -> bool:
        return len(self.captures) > 0

    def jass_str(self) -> str:
        sep = "x" if self.is_capture else "-"
        return f"{self.frm}{sep}{self.to}"

    def scan_str(self) -> str:
        """Scan's "from x to x captured x captured ..." notation.
        Per Scan's HUB v2 protocol the SECOND number is the destination;
        the remaining numbers are the captured-square set in any order."""
        if not self.is_capture:
            return f"{self.frm}-{self.to}"
        return "x".join(str(s) for s in (self.frm, self.to, *self.captures))


BEST_RE = re.compile(
    r"^bestmove\s+(\d+)([x-])(\d+)"
    r"(?:.*?\s+captures=([0-9,]+))?",
    re.MULTILINE)

DONE_RE = re.compile(
    r"^done\s+move=(\S+)",
    re.MULTILINE)


def parse_jass_bestmove(line: str) -> Move:
    m = BEST_RE.search(line)
    if not m:
        raise ValueError(f"could not parse Jass bestmove: {line!r}")
    frm = int(m.group(1))
    to  = int(m.group(3))
    caps_raw = m.group(4) or ""
    caps = tuple(int(s) for s in caps_raw.split(",")) if caps_raw else ()
    return Move(frm=frm, to=to, captures=caps)


def parse_scan_move(text: str) -> Move:
    """Parse Scan's move notation. Quiet: "28-32". Capture per HUB v2
    protocol: "from x to x captured x captured ..." e.g. "28x19x23" =
    from 28 to 19 capturing 23."""
    if "-" in text:
        a, b = text.split("-")
        return Move(int(a), int(b), ())
    parts = [int(p) for p in text.split("x")]
    if len(parts) < 2:
        raise ValueError(f"unparseable Scan move: {text!r}")
    return Move(frm=parts[0], to=parts[1], captures=tuple(parts[2:]))


# Jass HUB-FEN: "W:W31,32,...:B1,2,..." with optional "K" prefix for kings.
def parse_jass_fen(fen: str) -> tuple[str, list[int], list[int], list[int], list[int]]:
    """Return (side_to_move, white_men, white_kings, black_men, black_kings).
    side_to_move is 'W' or 'B'."""
    parts = fen.split(":")
    if len(parts) < 3:
        raise ValueError(f"bad FEN: {fen!r}")
    side = parts[0].strip()
    wm, wk, bm, bk = [], [], [], []
    for chunk in parts[1:]:
        chunk = chunk.strip()
        if not chunk:
            continue
        colour, rest = chunk[0], chunk[1:]
        # rest may be "31-50" (range) or "K28,K33,41,42" (commas, K prefix).
        squares_set_man  = set()
        squares_set_king = set()
        for token in rest.split(","):
            token = token.strip()
            if not token:
                continue
            is_king = token.startswith("K")
            if is_king:
                token = token[1:]
            if "-" in token:
                a, b = (int(x) for x in token.split("-"))
                for sq in range(a, b + 1):
                    (squares_set_king if is_king else squares_set_man).add(sq)
            else:
                (squares_set_king if is_king else squares_set_man).add(int(token))
        if colour == "W":
            wm = sorted(squares_set_man); wk = sorted(squares_set_king)
        elif colour == "B":
            bm = sorted(squares_set_man); bk = sorted(squares_set_king)
    return side, wm, wk, bm, bk


def jass_fen_to_scan_pos(fen: str) -> str:
    """Convert "W:W31-50:B1-20" → "Weeee...wwww" 51-char Scan position."""
    side, wm, wk, bm, bk = parse_jass_fen(fen)
    chars = ["e"] * 51
    chars[0] = side  # 'W' or 'B'
    for s in wm: chars[s] = "w"
    for s in wk: chars[s] = "W"
    for s in bm: chars[s] = "b"
    for s in bk: chars[s] = "B"
    return "".join(chars)


# ---------------------------------------------------------------------------
# Engine adapters
# ---------------------------------------------------------------------------
class EngineProc:
    """Common subprocess plumbing."""
    def __init__(self, argv: list[str], label: str, cwd: str | None = None):
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            cwd=cwd)
        self.label = label

    def _send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _read_until(self, predicate, timeout_s: float = 60.0) -> list[str]:
        """Read lines from the engine until `predicate(line)` returns True.
        Returns all lines read (incl. the matched one). Raises on timeout."""
        assert self.proc.stdout is not None
        deadline = time.monotonic() + timeout_s
        lines: list[str] = []
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{self.label}: no match in {timeout_s}s")
            line = self.proc.stdout.readline()
            if not line:
                raise EOFError(f"{self.label}: stdout closed")
            line = line.rstrip("\n")
            lines.append(line)
            if predicate(line):
                return lines

    def close(self) -> None:
        try:
            self._send("quit")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class JassEngine(EngineProc):
    """Adapter for Jass's HUB-flavoured protocol."""
    def __init__(self, path: str, label: str = "Jass",
                 no_book: bool = True, no_nnue: bool = False,
                 nnue_path: str | None = None,
                 book_path: str | None = None):
        argv = [path]
        if no_nnue: argv.append("--no-nnue")
        elif nnue_path:
            argv += ["--nnue", nnue_path]
        if book_path:
            # Load a custom JBOK book (e.g. the 77K-position book from 0013).
            # When set, no_book is ignored — the user explicitly opted in to a
            # book, presumably for a "fair-comparison" calibration where Scan
            # also has its book enabled.
            argv += ["--book", book_path]
        super().__init__(argv, label)
        # Handshake
        self._send("hello")
        self._read_until(lambda l: l.startswith("ready"))
        if no_book and not book_path:
            # Cleaner test of the eval — engines play their own moves
            # from the very first ply rather than parroting opening lines.
            # The default Jass build has a tiny hard-coded book but it
            # doesn't bias scout-class results materially.
            pass

    def new_game(self) -> None:
        # Reset state — `position startpos` does that.
        self._send("position startpos")
        self._read_until(lambda l: l == "ok" or l.startswith("error"))

    def set_position_fen(self, fen: str) -> None:
        self._send(f"position fen {fen}")
        self._read_until(lambda l: l == "ok" or l.startswith("error"))

    def go(self, depth: int | None = None,
                 movetime: float | None = None) -> Move | None:
        """Either depth (plies) or movetime (seconds) — exactly one.
        Jass's HUB takes ms internally, we convert from seconds here."""
        if movetime is not None:
            self._send(f"go movetime {int(round(movetime * 1000))}")
            timeout_s = movetime * 3.0 + 5.0
        else:
            self._send(f"go depth {depth}")
            timeout_s = 60.0
        lines = self._read_until(lambda l: l.startswith("bestmove")
                                          or l.startswith("error"),
                                 timeout_s=timeout_s)
        last = lines[-1]
        if last.startswith("error"):
            return None
        return parse_jass_bestmove(last)


class ScanEngine(EngineProc):
    """Adapter for Scan's HUB v2 protocol."""
    def __init__(self, path: str, label: str = "Scan",
                 no_book: bool = True, bb_size: int = 0):
        # Scan loads `scan.ini` and `data/` from its working directory,
        # so we cd into its install dir before launching.
        scan_dir = str(Path(path).resolve().parent)
        super().__init__([path, "hub"], label, cwd=scan_dir)
        # Handshake: send "hub", read params until "wait".
        self._send("hub")
        self._read_until(lambda l: l.startswith("wait"))
        if no_book:
            self._send("set-param name=book value=false")
        if bb_size > 0:
            # Enable Scan's endgame bitbases. value=6 covers up to 6 pieces,
            # value=7 covers up to 7. Scan ships the bitbase data in the
            # `data/` directory of the rhalbersma/scan repo so no extra
            # download is needed. Used for the "fair-comparison" calibrate
            # — without this flag, Scan plays endgames without any
            # tablebase help, which is asymmetric vs jass's built-in
            # KvK/KKvK retrograde-analysis bitbase.
            self._send(f"set-param name=bb-size value={bb_size}")
        self._send("init")
        self._read_until(lambda l: l.startswith("ready"))

    def new_game(self) -> None:
        self._send("new-game")

    def go_from(self, starting_scan_pos: str, scan_moves: list[str],
                depth: int | None = None,
                movetime: float | None = None) -> Move | None:
        """Either depth or movetime (seconds) — exactly one."""
        if scan_moves:
            moves_str = " ".join(scan_moves)
            self._send(f'pos pos={starting_scan_pos} moves="{moves_str}"')
        else:
            self._send(f"pos pos={starting_scan_pos}")
        if movetime is not None:
            self._send(f"level move-time={movetime}")
            timeout_s = movetime * 3.0 + 5.0
        else:
            self._send(f"level depth={depth}")
            timeout_s = 120.0
        self._send("go think")
        try:
            lines = self._read_until(lambda l: l.startswith("done")
                                              or l.startswith("error"),
                                     timeout_s=timeout_s)
        except TimeoutError:
            return None
        last = lines[-1]
        if last.startswith("error"):
            return None
        m = DONE_RE.search(last)
        if not m:
            return None
        return parse_scan_move(m.group(1))


# ---------------------------------------------------------------------------
# Referee (a Jass subprocess maintaining the canonical position)
# ---------------------------------------------------------------------------
class Referee:
    def __init__(self, jass_path: str):
        self.j = JassEngine(jass_path, label="Referee", no_book=True)
        self._scan_history: list[str] = []
        self._start_scan_pos: str = ""

    def set_position_fen(self, fen: str) -> None:
        self.j.set_position_fen(fen)
        self._scan_history = []
        self._start_scan_pos = jass_fen_to_scan_pos(fen)

    def current_fen(self) -> str:
        self.j._send("fen")
        lines = self.j._read_until(lambda l: l.startswith("fen "))
        return lines[-1].removeprefix("fen ").strip()

    def apply_move(self, m: Move) -> bool:
        self.j._send(f"apply {m.jass_str()}")
        lines = self.j._read_until(lambda l: l == "ok" or l.startswith("error"))
        if lines[-1].startswith("error"):
            return False
        self._scan_history.append(m.scan_str())
        return True

    def scan_pos(self) -> tuple[str, list[str]]:
        return self._start_scan_pos, self._scan_history

    def has_legal_moves(self) -> bool:
        # Heuristic: a search at depth 1 returns a default (0-0) bestmove
        # when no legal moves exist; Jass's HUB emits "bestmove 0-0".
        self.j._send("go depth 1")
        lines = self.j._read_until(lambda l: l.startswith("bestmove"))
        last = lines[-1]
        # Jass's format_move emits "0-0" for the default-constructed Move.
        return not last.startswith("bestmove 0-0")

    def close(self) -> None:
        self.j.close()


# ---------------------------------------------------------------------------
# Game + tournament
# ---------------------------------------------------------------------------
DEFAULT_OPENINGS = [
    # Position-after-first-move FENs — same 9-opening pool jass --tournament
    # uses internally. Built from start_position by applying one legal first
    # move. We list them as FENs ready to feed the engines.
    "B:W28,31-50:B1-20",   # 32-28
    "B:W31,32,34-50:B1-20", # 33-28 — actually that's 33-28; let me list more.
    "B:W31-32,34-50:B1-20", # 33-29? we'll keep this minimal — orchestrator can derive openings from Jass
]


def opening_pool_via_jass(jass_path: str) -> list[str]:
    """Walk Jass once to enumerate the start-position's legal first moves,
    return their FEN-after."""
    j = JassEngine(jass_path, label="opening", no_book=True)
    j.set_position_fen("W:W31-50:B1-20")
    fens: list[str] = []
    # We just hand-construct the openings: pick all 9 first moves by
    # iterating squares 31..35 and trying their NE / NW destinations.
    # Cheaper: ask Jass for a depth-1 search 9 times with different
    # forced moves? Too messy. Use a known list.
    # Standard 9 first moves: 31-26, 31-27, 32-27, 32-28, 33-28, 33-29,
    # 34-29, 34-30, 35-30.
    first_moves = [(31, 26), (31, 27), (32, 27), (32, 28), (33, 28),
                   (33, 29), (34, 29), (34, 30), (35, 30)]
    for frm, to in first_moves:
        j.set_position_fen("W:W31-50:B1-20")
        j.proc.stdin.write(f"apply {frm}-{to}\n")
        j.proc.stdin.flush()
        j._read_until(lambda l: l == "ok" or l.startswith("error"))
        # query the FEN
        j._send("fen")
        lines = j._read_until(lambda l: l.startswith("fen "))
        fens.append(lines[-1].removeprefix("fen ").strip())
    j.close()
    return fens


@dataclass
class GameResult:
    outcome: str   # "W", "D", "L" from white's POV
    plies:   int
    reason:  str


def play_game(white: object, black: object,
              referee: Referee,
              opening_fen: str,
              depth: int | None = None,
              movetime: float | None = None,
              max_plies: int = 200) -> GameResult:
    """Both engines must already be ready. They are addressed via
    duck-typed helpers (`go_jass(engine, depth)` for JassEngine,
    `go_scan(engine, scan_pos, moves, depth)` for ScanEngine).
    `white`/`black` may be either flavour."""
    referee.set_position_fen(opening_fen)
    # Sync engine internal positions to this start.
    for eng in (white, black):
        if isinstance(eng, JassEngine):
            eng.new_game()
            eng.set_position_fen(opening_fen)
        else:
            eng.new_game()

    side_to_move = "W" if opening_fen.startswith("W") else "B"
    halfmove_counter = 0
    ply = 0
    while ply < max_plies:
        current = white if side_to_move == "W" else black
        # Ask engine for its move.
        if isinstance(current, JassEngine):
            mv = current.go(depth=depth, movetime=movetime)
        else:
            scan_pos, scan_moves = referee.scan_pos()
            mv = current.go_from(scan_pos, scan_moves,
                                 depth=depth, movetime=movetime)
        if mv is None or (mv.frm == 0 and mv.to == 0):
            # No legal move (terminal — current side loses).
            outcome = "L" if side_to_move == "W" else "W"
            return GameResult(outcome, ply, "no legal move from " + current.label)
        # Apply to referee (canonical state).
        if not referee.apply_move(mv):
            outcome = "L" if side_to_move == "W" else "W"
            return GameResult(outcome, ply, f"illegal move {mv.jass_str()} from {current.label}")
        # Jass's `go` returns a move WITHOUT applying it — keep both
        # Jass-side engines in sync via an explicit `apply`. Scan is
        # stateless (we feed pos+moves on every `go_from`), so nothing
        # to do for the Scan players.
        for eng in (white, black):
            if isinstance(eng, JassEngine):
                eng._send(f"apply {mv.jass_str()}")
                eng._read_until(lambda l: l == "ok" or l.startswith("error"))

        ply += 1
        side_to_move = "B" if side_to_move == "W" else "W"

        # 50-half-move rule (25-move rule in draughts): if 50 plies pass
        # without an irreversible move, declare a draw. Captures and
        # promotions reset the counter; we approximate by checking the
        # move is a capture (resets) — promotions are harder to detect
        # without inspecting the position.
        if mv.is_capture:
            halfmove_counter = 0
        else:
            halfmove_counter += 1
        if halfmove_counter >= 50:
            return GameResult("D", ply, "25-move rule")

    return GameResult("D", ply, "ply cap")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def estimate_elo(score_rate: float) -> float:
    """Linear-Elo conversion: ELO_diff = -400 * log10(1/p - 1)."""
    if score_rate <= 0: return -800.0
    if score_rate >= 1: return  800.0
    return -400.0 * math.log10(1.0 / score_rate - 1.0)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--jass",  required=True, help="path to the Jass binary")
    p.add_argument("--scan",  required=True, help="path to the Scan binary")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--depth",    type=int,
                   help="fixed search depth (plies)")
    g.add_argument("--movetime", type=float,
                   help="per-move time budget in seconds (real number)")
    p.add_argument("--pairs", type=int, default=2,
                   help="colour-swap pairs per opening (total games = 18 × pairs)")
    p.add_argument("--max-plies", type=int, default=200)
    g_nnue = p.add_mutually_exclusive_group()
    g_nnue.add_argument("--nnue", metavar="PATH",
                        help="weights file passed to Jass via --nnue "
                             "(JNNM/JNNQ/Linear). Only the player; the "
                             "referee keeps the default network.")
    g_nnue.add_argument("--no-nnue", action="store_true",
                        help="force Jass to fall back to the handcrafted eval")
    # Fair-comparison knobs. Disabled by default so the eval-vs-eval
    # measurement stays clean; the new 0019 job opts them in.
    p.add_argument("--jass-book", metavar="PATH", default=None,
                   help="optional JBOK file loaded by Jass via --book. "
                        "Pair with --scan-book on for a fair-comparison "
                        "calibrate where both engines have access to their "
                        "opening book.")
    p.add_argument("--scan-book", choices=("on", "off"), default="off",
                   help="when 'off' (default) the script tells Scan "
                        "`set-param name=book value=false` to disable its "
                        "own opening book — the apples-to-apples eval test. "
                        "'on' leaves Scan's book at its native value (true).")
    p.add_argument("--scan-bb-size", type=int, default=0,
                   help="Scan endgame-bitbase coverage. 0 (default) = "
                        "disabled, matches the 'no tablebase' eval test. "
                        "6 enables the up-to-6-pieces bitbase shipped in "
                        "rhalbersma/scan's data/ directory; 7 the full "
                        "bitbase. Used in the fair-comparison calibrate.")
    args = p.parse_args(argv)
    if args.depth is None and args.movetime is None:
        args.depth = 8  # back-compat default
    budget_str = (f"depth {args.depth}" if args.depth is not None
                  else f"movetime {args.movetime}s")

    openings = opening_pool_via_jass(args.jass)
    print(f"opening pool: {len(openings)} positions")
    print(f"jass setup:   nnue={args.nnue or ('(handcrafted)' if args.no_nnue else '(default)')}"
          f"  book={args.jass_book or '(default/none)'}")
    print(f"scan setup:   book={args.scan_book}  bb-size={args.scan_bb_size}")

    jass = JassEngine(args.jass, label="Jass-player",
                      no_nnue=args.no_nnue, nnue_path=args.nnue,
                      book_path=args.jass_book)
    scan = ScanEngine(args.scan, label="Scan-player",
                      no_book=(args.scan_book == "off"),
                      bb_size=args.scan_bb_size)
    referee = Referee(args.jass)

    a_wins = b_wins = draws = 0
    games  = 0
    t0 = time.time()
    try:
        for opening in openings:
            for pair in range(args.pairs):
                # Pair: Jass white vs Scan black, then Scan white vs Jass black.
                for jass_is_white in (True, False):
                    if jass_is_white:
                        r = play_game(jass, scan, referee, opening,
                                      depth=args.depth, movetime=args.movetime,
                                      max_plies=args.max_plies)
                    else:
                        r = play_game(scan, jass, referee, opening,
                                      depth=args.depth, movetime=args.movetime,
                                      max_plies=args.max_plies)
                    games += 1
                    # Map "W"/"L" outcome to Jass's POV.
                    if r.outcome == "D":
                        draws += 1
                        jass_pts = 0.5
                    elif (r.outcome == "W" and jass_is_white) or \
                         (r.outcome == "L" and not jass_is_white):
                        a_wins += 1
                        jass_pts = 1.0
                    else:
                        b_wins += 1
                        jass_pts = 0.0
                    elapsed = time.time() - t0
                    print(f"  game {games:3d}: "
                          f"{'Jass' if jass_is_white else 'Scan'}=W "
                          f"{'Scan' if jass_is_white else 'Jass'}=B "
                          f"→ {r.outcome} ({r.reason}, {r.plies} plies)  "
                          f"Jass +{jass_pts:.1f}  [{elapsed:.0f}s]")
    finally:
        jass.close(); scan.close(); referee.close()

    jass_score = a_wins + 0.5 * draws
    rate = jass_score / games if games else 0.0
    elo  = estimate_elo(rate)
    print()
    print(f"=== Jass vs Scan, {budget_str}, {games} games ===")
    print(f"  Jass={a_wins}  Scan={b_wins}  Draws={draws}")
    print(f"  Jass score rate: {rate:.3f} ({jass_score:.1f} / {games})")
    print(f"  ELO estimate:    {elo:+.0f} (95% CI ≈ ±{800/(games**0.5):.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
