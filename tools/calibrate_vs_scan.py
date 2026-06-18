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
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
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
    """Common subprocess plumbing.

    stdout is consumed by a dedicated reader thread into a queue. This is
    what makes `_drain()` reliable: a naive `select`-based drain misses
    lines already pulled into Python's `readline` buffer, so stale engine
    output (notably a `done` from a prior search) accumulates over a long
    match and eventually makes every read off-by-one — once a stale move
    is returned the drift compounds and every later game forfeits at 0-1
    plies on an illegal (stale) move. The reader thread pulls *every* line
    out of the OS pipe immediately, so draining the queue discards all
    pending output and re-aligns read<->command. (Diagnosed on the
    fixed-depth calibrate match vs Scan, job 0137.)"""
    def __init__(self, argv: list[str], label: str, cwd: str | None = None):
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            cwd=cwd)
        self.label = label
        self._q: queue.Queue = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._q.put(line.rstrip("\n"))
        self._q.put(None)  # EOF sentinel

    def _send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _drain(self) -> None:
        """Discard any pending output so the next `_read_until` aligns
        with the command we are about to send. Empties the reader queue
        (the thread has already pulled everything out of the pipe)."""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    def _read_until(self, predicate, timeout_s: float = 60.0) -> list[str]:
        """Read lines from the engine until `predicate(line)` returns True.
        Returns all lines read (incl. the matched one). Raises on timeout."""
        deadline = time.monotonic() + timeout_s
        lines: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{self.label}: no match in {timeout_s}s")
            try:
                line = self._q.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if line is None:
                raise EOFError(f"{self.label}: stdout closed")
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
                 pattern_path: str | None = None,
                 book_path: str | None = None,
                 threads: int = 1):
        argv = [path]
        if pattern_path:
            # Play with a pattern eval (PJTW) — lets us benchmark a pattern
            # engine vs Scan. Takes precedence over nnue.
            argv += ["--pattern", pattern_path]
        elif no_nnue: argv.append("--no-nnue")
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
        if threads > 1:
            # Lazy SMP : fan out search across N threads via shared TT.
            self._send(f"set-param name=threads value={threads}")
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
        self._drain()  # re-align: discard any stale buffered output first
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
        # Set bb-size EXPLICITLY (never inherit scan.ini's default) so the
        # comparison is reproducible and auditable, regardless of what the
        # shipped scan.ini says or whether bitbase files happen to be present:
        #   bb_size == 0 → Scan plays endgames with NO tablebase help. This is
        #     the FAIR eval+search comparison vs jass (which has only a trivial
        #     built-in KvK/KKvK bitbase — negligible).
        #   bb_size >= 2 → Scan uses its 2..N-piece bitbases ("full handicap").
        #     NB the bitbase data is NOT bundled in the rhalbersma/scan git
        #     repo — it's a separate ~706 MiB download (hjetten's site), so
        #     bb_size>0 only has effect once those files are installed.
        self._send(f"set-param name=bb-size value={bb_size}")
        self._send("init")
        init_lines = self._read_until(lambda l: l.startswith("ready"))
        # Make the bench log show exactly what was configured/loaded.
        for ln in init_lines:
            if ln and not ln.startswith("ready"):
                print(f"  [{self.label} init] {ln}")
        print(f"  [{self.label}] bb-size={bb_size} "
              + ("(no bitbases — FAIR comparison)" if bb_size == 0
                 else "(WITH bitbases — handicap comparison)"))

    def new_game(self) -> None:
        self._send("new-game")

    def go_from(self, starting_scan_pos: str, scan_moves: list[str],
                depth: int | None = None,
                movetime: float | None = None) -> Move | None:
        """Either depth or movetime (seconds) — exactly one."""
        self._drain()  # re-align: discard any stale buffered output first
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
    # Optional move/FEN history for post-hoc analysis (piece count by phase,
    # eval drift detection). Populated only when the caller explicitly
    # captures them ; defaults to empty for back-compat.
    moves:   list[str] = field(default_factory=list)
    fens:    list[str] = field(default_factory=list)


def play_game(white: object, black: object,
              referee: Referee,
              opening_fen: str,
              depth: int | None = None,
              movetime: float | None = None,
              jass_depth: int | None = None,
              scan_depth: int | None = None,
              jass_movetime: float | None = None,
              scan_movetime: float | None = None,
              max_plies: int = 200) -> GameResult:
    """Both engines must already be ready. They are addressed via
    duck-typed helpers (`go_jass(engine, depth)` for JassEngine,
    `go_scan(engine, scan_pos, moves, depth)` for ScanEngine).
    `white`/`black` may be either flavour. `jass_depth`/`scan_depth`, when
    set, override `depth` for that side (asymmetric-depth diagnostic)."""
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
    moves_log: list[str] = []
    fens_log:  list[str] = [opening_fen]
    while ply < max_plies:
        current = white if side_to_move == "W" else black
        # Ask engine for its move.
        if isinstance(current, JassEngine):
            d = jass_depth if jass_depth is not None else depth
            mt = jass_movetime if jass_movetime is not None else movetime
            mv = current.go(depth=d, movetime=mt)
        else:
            scan_pos, scan_moves = referee.scan_pos()
            # Per-engine defaults let two Scan instances of DIFFERENT strength
            # (e.g. strong depth-9 vs weak depth-5) face off in one game — used by
            # scan_selfplay_gen to force decisive, diverse self-play positions.
            d = scan_depth if scan_depth is not None else (
                getattr(current, "default_depth", None) or depth)
            mt = scan_movetime if scan_movetime is not None else (
                getattr(current, "default_movetime", None) or movetime)
            mv = current.go_from(scan_pos, scan_moves,
                                 depth=d, movetime=mt)
        if mv is None or (mv.frm == 0 and mv.to == 0):
            # No legal move (terminal — current side loses).
            outcome = "L" if side_to_move == "W" else "W"
            return GameResult(outcome, ply, "no legal move from " + current.label,
                              moves=moves_log, fens=fens_log)
        # Apply to referee (canonical state).
        if not referee.apply_move(mv):
            outcome = "L" if side_to_move == "W" else "W"
            return GameResult(outcome, ply, f"illegal move {mv.jass_str()} from {current.label}",
                              moves=moves_log, fens=fens_log)
        moves_log.append(mv.jass_str())
        fens_log.append(referee.current_fen())
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
            return GameResult("D", ply, "25-move rule",
                              moves=moves_log, fens=fens_log)

    return GameResult("D", ply, "ply cap",
                      moves=moves_log, fens=fens_log)


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
                   help="per-move time budget in SECONDS — NOT milliseconds! "
                        "e.g. 0.5 = half a second/move, 1 = one second/move. "
                        "(Jass's HUB is ms internally; this flag converts s->ms. "
                        "Passing 500 means 500 s/move = ~16 h/game — the 0237/0243 hang.)")
    # Asymmetric fixed-depth: give one side a different depth from --depth.
    # Used by the eval-vs-search diagnostic (how many extra plies does Jass
    # need to match Scan at a fixed Scan depth). Each overrides --depth for
    # its side; ignored under --movetime.
    p.add_argument("--allow-long-movetime", action="store_true",
                   help="override the >30s/move sanity guard (rare; for genuinely "
                        "long per-move budgets). Without it, --movetime>30 aborts as "
                        "a likely seconds/ms units error.")
    p.add_argument("--jass-depth", type=int, default=None,
                   help="override search depth for the Jass side (plies)")
    p.add_argument("--scan-depth", type=int, default=None,
                   help="override search depth for the Scan side (plies)")
    # PERMANENT METHODOLOGY (2026-06-18): an equal fixed --movetime vs Scan is
    # NOT a fair comparison — it conflates eval quality with search SPEED (jass'
    # NPS << Scan, so equal time = jass sees fewer plies and loses regardless of
    # eval). The standard comparison is FIXED DEPTH (--depth / --jass-depth +
    # --scan-depth) OR NPS-COMPENSATED movetime: give the slower engine more time
    # in proportion to the NPS gap (e.g. jass 2x slower → --jass-movetime 1.0
    # --scan-movetime 0.5). See docs/SCAN_METHODOLOGY_GAP.md.
    p.add_argument("--jass-movetime", type=float, default=None,
                   help="per-move time budget (SECONDS) for the Jass side only — "
                        "use with --scan-movetime to NPS-compensate (fair).")
    p.add_argument("--scan-movetime", type=float, default=None,
                   help="per-move time budget (SECONDS) for the Scan side only.")
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
    g_nnue.add_argument("--jass-pattern", metavar="PATH",
                        help="PJTW pattern weights — play the Jass side with a "
                             "pattern eval (vs Scan). Only the player.")
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
    p.add_argument("--dump-games-dir", metavar="DIR", default=None,
                   help="if set, dumps one JSON per game with the full move "
                        "history + outcome metadata. Required input to "
                        "tools/analyze_loss_by_pieces.py for post-hoc "
                        "diagnostic of where jass wins/loses by piece count.")
    p.add_argument("--jass-threads", type=int, default=1,
                   help="Lazy SMP : number of threads for the jass player "
                        "(via HUB `set-param name=threads value=N`). Default "
                        "1. Use with --movetime to see SMP gain — fixed depth "
                        "saturates at the eval ceiling and doesn't surface "
                        "the depth-per-second advantage SMP gives.")
    args = p.parse_args(argv)
    # UNITS GUARD : --movetime is per-move SECONDS, not ms. The trap is that
    # `jass --depth-at-movetime` and the Jass HUB `go movetime` are MILLISECONDS,
    # so passing 500/1000 (ms-thinking) here = 500/1000 s/move = hours/game with
    # ZERO output (the 0237/0243 hang, ~4h for 0 games). Nobody intends >30s/move
    # for these gauntlets, so refuse it as a near-certain units error.
    if args.movetime is not None and args.movetime > 30.0 and not args.allow_long_movetime:
        sys.exit(f"ABORT: --movetime {args.movetime} is per-move SECONDS (not ms). "
                 f"{args.movetime}s/move x ~120 plies ~= {args.movetime*120/3600:.1f} h/game "
                 f"-> the match never finishes. Did you mean --movetime "
                 f"{args.movetime/1000:g}? Use seconds (e.g. 0.5, 1), or pass "
                 f"--allow-long-movetime to override.")
    if args.movetime is not None and args.movetime <= 0:
        sys.exit("ABORT: --movetime must be > 0 seconds.")
    _any_timing = any(v is not None for v in (
        args.depth, args.movetime, args.jass_depth, args.scan_depth,
        args.jass_movetime, args.scan_movetime))
    if not _any_timing:
        args.depth = 8  # back-compat default
    if args.jass_movetime is not None and args.jass_movetime > 30.0 and not args.allow_long_movetime:
        sys.exit("ABORT: --jass-movetime is per-move SECONDS; >30 is a units error "
                 "(pass --allow-long-movetime to override).")
    if args.scan_movetime is not None and args.scan_movetime > 30.0 and not args.allow_long_movetime:
        sys.exit("ABORT: --scan-movetime is per-move SECONDS; >30 is a units error "
                 "(pass --allow-long-movetime to override).")
    # FAIRNESS GUARD (permanent methodology, 2026-06-18): an equal fixed --movetime
    # vs Scan conflates eval quality with search SPEED. Warn loudly; the standard is
    # fixed depth or NPS-compensated per-side movetime. (Not an abort — sometimes you
    # genuinely want the equal-time number, e.g. to MEASURE the speed handicap.)
    _symmetric_time = (args.movetime is not None and args.jass_movetime is None
                       and args.scan_movetime is None and args.depth is None
                       and args.jass_depth is None and args.scan_depth is None)
    if _symmetric_time:
        print("  ⚠️  EQUAL fixed-time vs Scan is NOT a fair eval comparison "
              "(jass NPS << Scan → fewer plies). Standard = --depth/--jass-depth "
              "+--scan-depth, or NPS-compensated --jass-movetime/--scan-movetime. "
              "See docs/SCAN_METHODOLOGY_GAP.md.", flush=True)
    budget_str = (f"depth {args.depth}" if args.depth is not None
                  else (f"jass_mt={args.jass_movetime}s/scan_mt={args.scan_movetime}s"
                        if (args.jass_movetime or args.scan_movetime) is not None
                        else f"movetime {args.movetime}s"))

    dump_dir = None
    if args.dump_games_dir:
        from pathlib import Path
        import json
        dump_dir = Path(args.dump_games_dir)
        dump_dir.mkdir(parents=True, exist_ok=True)
        print(f"dumping per-game JSONs to: {dump_dir}")

    openings = opening_pool_via_jass(args.jass)
    print(f"opening pool: {len(openings)} positions")
    eval_desc = (f"pattern={args.jass_pattern}" if args.jass_pattern
                 else f"nnue={args.nnue or ('(handcrafted)' if args.no_nnue else '(default)')}")
    print(f"jass setup:   {eval_desc}  book={args.jass_book or '(default/none)'}")
    print(f"scan setup:   book={args.scan_book}  bb-size={args.scan_bb_size}")

    jass = JassEngine(args.jass, label="Jass-player",
                      no_nnue=args.no_nnue, nnue_path=args.nnue,
                      pattern_path=args.jass_pattern,
                      book_path=args.jass_book,
                      threads=args.jass_threads)
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
                                      jass_depth=args.jass_depth, scan_depth=args.scan_depth,
                                      jass_movetime=args.jass_movetime, scan_movetime=args.scan_movetime,
                                      max_plies=args.max_plies)
                    else:
                        r = play_game(scan, jass, referee, opening,
                                      depth=args.depth, movetime=args.movetime,
                                      jass_depth=args.jass_depth, scan_depth=args.scan_depth,
                                      jass_movetime=args.jass_movetime, scan_movetime=args.scan_movetime,
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
                    if dump_dir is not None:
                        # Referee's move history was reset by the next
                        # play_game's set_position_fen — capture here BEFORE
                        # the loop iterates. But play_game doesn't expose
                        # the history nicely ; we accept it's already-reset
                        # by the time we get here. Workaround : reach into
                        # referee BEFORE the reset. Simpler : add to
                        # GameResult. For now, emit metadata-only JSON.
                        out_json = dump_dir / f"game-{games:03d}.json"
                        out_json.write_text(json.dumps({
                            "game_id": games,
                            "opening": opening,
                            "jass_is_white": jass_is_white,
                            "outcome": r.outcome,
                            "reason": r.reason,
                            "plies": r.plies,
                            "jass_score": jass_pts,
                            "moves": list(getattr(r, "moves", [])),
                            "fens":  list(getattr(r, "fens",  [])),
                        }, indent=2))
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
