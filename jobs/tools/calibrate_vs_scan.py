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

    def jass_apply_str(self) -> str:
        """Losslessly identify a move for Jass's HUB `apply` command."""
        if not self.is_capture:
            return self.jass_str()
        captured = ",".join(str(square) for square in sorted(self.captures))
        return f"{self.jass_str()} captures={captured}"

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
    if m.group(2) == "x" and not caps:
        raise ValueError(f"Jass capture lacks captured-square identity: {line!r}")
    return Move(frm=frm, to=to, captures=caps)


def parse_scan_move(text: str) -> Move:
    """Parse Scan's move notation. Quiet: "28-32". Capture per HUB v2
    protocol: "from x to x captured x captured ..." e.g. "28x19x23" =
    from 28 to 19 capturing 23."""
    if "-" in text:
        a, b = text.split("-")
        return Move(int(a), int(b), ())
    parts = [int(p) for p in text.split("x")]
    if len(parts) < 3:
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


def _advance_25_move_clock(counter: int, fen_before: str, move: Move) -> int:
    """Advance the FMJD 25-move clock after ``move``.

    Only a quiet king move advances the clock. A capture or any man move
    resets it, including a move that promotes the man on its destination
    square. Inspecting the origin in the pre-move FEN avoids having to infer
    promotion from the destination row.
    """
    if move.is_capture:
        return 0

    side, white_men, _, black_men, _ = parse_jass_fen(fen_before)
    if side == "W":
        moved_man = move.frm in white_men
    elif side == "B":
        moved_man = move.frm in black_men
    else:
        raise ValueError(f"bad side to move in FEN: {fen_before!r}")

    return 0 if moved_man else counter + 1


def _repetition_key(fen: str) -> tuple:
    """Canonical board+side key for FMJD repetition adjudication."""
    side, white_men, white_kings, black_men, black_kings = parse_jass_fen(fen)
    return (
        side,
        tuple(white_men), tuple(white_kings),
        tuple(black_men), tuple(black_kings),
    )


# ---------------------------------------------------------------------------
# Engine adapters
# ---------------------------------------------------------------------------
class EngineFailure(RuntimeError):
    """An engine failed to answer a search it was asked to run.

    Raised, never scored. An engine that errors out or times out is not a
    side that has run out of moves, and turning one into the other silently
    manufactures a result: a broken binary would read as a crushing defeat
    and be published as strength. The cell must abort loudly instead
    (project rule: n=0 is a failure, not a neutral outcome)."""


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


def jass_argv(path: str, no_book: bool = True, no_nnue: bool = False,
              nnue_path: str | None = None,
              pattern_path: str | None = None,
              book_path: str | None = None,
              search_params: str | None = None,
              enforce_no_book: bool = False) -> list[str]:
    """Command line for a Jass player. Split out of `JassEngine` so the
    book/eval/search wiring can be asserted without spawning a binary."""
    argv = [path]
    if pattern_path:
        # Play with a pattern eval (PJTW) — lets us benchmark a pattern
        # engine vs Scan. Takes precedence over nnue.
        argv += ["--pattern", pattern_path]
    elif no_nnue:
        argv.append("--no-nnue")
    elif nnue_path:
        argv += ["--nnue", nnue_path]
    if search_params:
        # Override the HUB engine's search constants (LMR/pruning/etc.)
        # WITHOUT a rebuild — tune search vs Scan in one build.
        argv += ["--search-params", search_params]
    if book_path:
        # Load a custom JBOK book (e.g. the 77K-position book from 0013).
        # When set, no_book is ignored — the user explicitly opted in to a
        # book, presumably for a "fair-comparison" calibration where Scan
        # also has its book enabled.
        argv += ["--book", book_path]
    elif no_book and enforce_no_book:
        argv.append("--no-book")
    return argv


class JassEngine(EngineProc):
    """Adapter for Jass's HUB-flavoured protocol."""
    def __init__(self, path: str, label: str = "Jass",
                 no_book: bool = True, no_nnue: bool = False,
                 nnue_path: str | None = None,
                 pattern_path: str | None = None,
                 book_path: str | None = None,
                 search_params: str | None = None,
                 threads: int = 1,
                 enforce_no_book: bool = False):
        argv = jass_argv(path, no_book=no_book, no_nnue=no_nnue,
                         nnue_path=nnue_path, pattern_path=pattern_path,
                         book_path=book_path, search_params=search_params,
                         enforce_no_book=enforce_no_book)
        super().__init__(argv, label)
        # Handshake
        self._send("hello")
        self._read_until(lambda l: l.startswith("ready"))
        if threads > 1:
            # Lazy SMP : fan out search across N threads via shared TT.
            self._send(f"setoption threads {threads}")
            configured = self._read_until(
                lambda l: l == "ok" or l.startswith("error")
            )
            if configured[-1].startswith("error"):
                self.close()
                raise RuntimeError(
                    f"{self.label}: could not set Jass threads={threads}"
                )
        # `no_book` alone is a declaration of intent, not an effect: until
        # `--no-book` existed the Jass side always consulted its built-in
        # book while Scan ran `book=off`. `enforce_no_book` is what actually
        # removes that asymmetry, and it is opt-in so that a run stays
        # comparable with the gates published before the flag existed.
        self.book_disabled = bool(no_book and enforce_no_book
                                  and not book_path)

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
            # x5 (au lieu de x3) : tolère le bug overshoot movetime-endgame (2-3.5x) aux longs
            # mt (headroom / prof-soi-long) — jass finit son coup au lieu d'un faux-timeout.
            timeout_s = movetime * 5.0 + 10.0
        else:
            self._send(f"go depth {depth}")
            timeout_s = 60.0
        lines = self._read_until(lambda l: l.startswith("bestmove")
                                          or l.startswith("error"),
                                 timeout_s=timeout_s)
        last = lines[-1]
        if last.startswith("error"):
            raise EngineFailure(f"{self.label}: {last}")
        return parse_jass_bestmove(last)


class ScanEngine(EngineProc):
    """Adapter for Scan's HUB v2 protocol."""

    RUNTIME_PARAMS = (
        ("variant", "normal"),
        ("book", "false"),
        ("book-ply", "4"),
        ("book-margin", "4"),
        ("ponder", "false"),
        ("threads", "1"),
        ("tt-size", "24"),
        ("bb-size", "0"),
    )

    @staticmethod
    def _hub_params(lines: Iterable[str]) -> dict[str, str]:
        params: dict[str, str] = {}
        for line in lines:
            match = re.match(r"^param name=(\S+) value=(\S+)(?:\s|$)", line)
            if match:
                params[match.group(1)] = match.group(2).strip('"')
        return params

    def __init__(self, path: str, label: str = "Scan",
                 no_book: bool = True, bb_size: int = 0):
        if not no_book or bb_size != 0:
            raise ValueError(
                "the pinned Scan runtime contract requires no_book=True and bb_size=0"
            )
        # Scan loads `scan.ini` and `data/` from its working directory,
        # so we cd into its install dir before launching.
        scan_dir = str(Path(path).resolve().parent)
        super().__init__([path, "hub"], label, cwd=scan_dir)
        # Handshake: send "hub", read params until "wait".
        try:
            self._send("hub")
            first_hub = self._read_until(lambda l: l.startswith("wait"))
        except BaseException:
            self.close()
            raise
        expected_names = {name for name, _ in self.RUNTIME_PARAMS}
        if set(self._hub_params(first_hub)) != expected_names:
            self.close()
            raise RuntimeError("unexpected Scan HUB parameter schema")
        try:
            for name, value in self.RUNTIME_PARAMS:
                self._send(f"set-param name={name} value={value}")
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
            self._send("hub")
            effective_lines = self._read_until(lambda l: l.startswith("wait"))
        except BaseException:
            self.close()
            raise
        if not any(
            line.startswith("id name=Scan version=3.1")
            for line in effective_lines
        ):
            self.close()
            raise RuntimeError("unexpected Scan identity")
        effective = self._hub_params(effective_lines)
        expected = dict(self.RUNTIME_PARAMS)
        if effective != expected:
            self.close()
            raise RuntimeError(
                f"Scan effective parameters mismatch: {effective!r} != {expected!r}"
            )
        try:
            self._send("init")
            init_lines = self._read_until(
                lambda l: l.startswith("ready") or l.startswith("error")
            )
        except BaseException:
            self.close()
            raise
        if not init_lines[-1].startswith("ready"):
            self.close()
            raise RuntimeError(f"Scan init failed: {init_lines[-1]}")
        # Make the bench log show exactly what was configured/loaded.
        for ln in init_lines:
            if ln and not ln.startswith("ready"):
                print(f"  [{self.label} init] {ln}")
        print(f"  [{self.label}] pinned HUB params={effective}")

    def new_game(self) -> None:
        self._send("new-game")

    def go_from(self, starting_scan_pos: str, scan_moves: list[str],
                depth: int | None = None,
                movetime: float | None = None) -> Move | None:
        """Either depth or movetime (seconds) — exactly one."""
        return self.go_from_verbose(starting_scan_pos, scan_moves,
                                    depth=depth, movetime=movetime)[0]

    def go_from_verbose(self, starting_scan_pos: str, scan_moves: list[str],
                        depth: int | None = None,
                        movetime: float | None = None
                        ) -> tuple[Move | None, list[str]]:
        """Comme `go_from`, mais rend AUSSI les lignes brutes de Scan.

        Le coup seul suffit pour jouer une partie ; l'atlas de points aveugles a
        besoin du **score**, que Scan ne met que sur ses lignes `info` et jamais
        sur `done` (vérifié le 2026-07-31, cf
        `docs/experiments/L3_SCAN_SCORE_FORMAT_20260731.md`). Plutôt que de
        redupliquer le protocole HUB dans un second outil — deux implémentations
        qui dérivent — on expose les lignes ici et `go_from` délègue, donc les
        appelants historiques ne changent pas de comportement."""
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
        except TimeoutError as exc:
            raise EngineFailure(
                f"{self.label}: no `done` within {timeout_s:.1f}s") from exc
        last = lines[-1]
        if last.startswith("error"):
            raise EngineFailure(f"{self.label}: {last}")
        m = DONE_RE.search(last)
        if not m:
            if last.strip() == "done":
                # A bare `done` is how Scan says "I have no move": the position
                # is terminal for the side to move. That is a legitimate game
                # end, not a protocol failure — the caller confirms it against
                # the referee's move generator before scoring it. Raising here
                # aborted every cell of home-0999 and home-1000.
                return None, lines
            raise EngineFailure(f"{self.label}: unparsable reply {last!r}")
        return parse_scan_move(m.group(1)), lines


# ---------------------------------------------------------------------------
# Referee (a Jass subprocess maintaining the canonical position)
# ---------------------------------------------------------------------------
class Referee:
    def __init__(self, jass_path: str):
        self.j = JassEngine(jass_path, label="Referee", no_book=True)
        self._jass_path = jass_path
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
        self.j._send(f"apply {m.jass_apply_str()}")
        lines = self.j._read_until(lambda l: l == "ok" or l.startswith("error"))
        if lines[-1].startswith("error"):
            return False
        self._scan_history.append(m.scan_str())
        return True

    def scan_pos(self) -> tuple[str, list[str]]:
        return self._start_scan_pos, self._scan_history

    def has_legal_moves(self) -> bool:
        """Legality straight from move generation, never from search.

        This used to ask the referee for `go depth 1` and read a `bestmove
        0-0` as "no legal move". The referee is the same binary as the
        player, so any bug that made the player return a null move made the
        referee agree — and the guard that is supposed to catch a failed
        engine confirmed the failure instead. That is exactly how a drawn
        root (repetition, 50-ply) was scored as a lost game for years.
        `--perft 1` counts generated moves in a fresh process and shares no
        code path with the search.
        """
        out = subprocess.run(
            [self._jass_path, "--perft", "1", self.current_fen()],
            capture_output=True, text=True, timeout=60)
        m = re.search(r"perft\(1\)\s*=\s*(\d+)", out.stdout)
        if not m:
            raise EngineFailure(
                f"referee perft failed: {out.stdout!r} {out.stderr!r}")
        return int(m.group(1)) > 0

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
              max_plies: int = 200,
              game_timeout_s: float | None = None) -> GameResult:
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
    repetition_counts = {_repetition_key(opening_fen): 1}
    game_deadline = (time.monotonic() + game_timeout_s) if game_timeout_s else None
    while ply < max_plies:
        # Per-game wall-clock cap → draw. Bounds the movetime-endgame overshoot
        # bug: individual moves stay under the per-move timeout but accumulate
        # to tens of minutes, so cap the whole game instead of hanging the gate.
        if game_deadline is not None and time.monotonic() > game_deadline:
            # A move that consumed the remaining budget may also have ended the
            # game. Preserve the canonical terminal-before-adjudication order.
            if not referee.has_legal_moves():
                outcome = "L" if side_to_move == "W" else "W"
                next_player = white if side_to_move == "W" else black
                return GameResult(
                    outcome, ply, "no legal move from " + next_player.label,
                    moves=moves_log, fens=fens_log)
            return GameResult("D", ply, "game time cap",
                              moves=moves_log, fens=fens_log)
        current = white if side_to_move == "W" else black
        # Ask engine for its move.
        if isinstance(current, JassEngine):
            # Per-engine defaults (like the Scan branch below) let two JassEngine
            # instances of DIFFERENT strength (strong vs weak depth/movetime) face
            # off in one game — used by scan_selfplay_gen --player-jass for
            # CHAMPION self-asym (moving-distribution chain, autonomous teacher).
            d = jass_depth if jass_depth is not None else (
                getattr(current, "default_depth", None) or depth)
            mt = jass_movetime if jass_movetime is not None else (
                getattr(current, "default_movetime", None) or movetime)
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
            # "No move" is only credible when the referee agrees the position
            # is terminal. Otherwise the engine failed to search, and scoring
            # that as a loss would publish a broken binary as a weak one.
            if referee.has_legal_moves():
                raise EngineFailure(
                    f"{current.label}: returned no move at ply {ply} in a "
                    f"position with legal moves ({fens_log[-1]})")
            # No legal move (terminal — current side loses).
            outcome = "L" if side_to_move == "W" else "W"
            return GameResult(outcome, ply, "no legal move from " + current.label,
                              moves=moves_log, fens=fens_log)
        # Apply to referee (canonical state).
        fen_before_move = fens_log[-1]
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
                eng._send(f"apply {mv.jass_apply_str()}")
                applied = eng._read_until(
                    lambda l: l == "ok" or l.startswith("error")
                )
                if applied[-1].startswith("error"):
                    raise RuntimeError(
                        f"{eng.label}: exact move synchronization failed: "
                        f"{mv.jass_apply_str()}"
                    )

        ply += 1
        side_to_move = "B" if side_to_move == "W" else "W"

        # 50-half-move rule (25-move rule in draughts): only quiet king
        # moves advance the counter; captures and all man moves reset it.
        halfmove_counter = _advance_25_move_clock(
            halfmove_counter, fen_before_move, mv)
        position_key = _repetition_key(fens_log[-1])
        repetition_counts[position_key] = repetition_counts.get(position_key, 0) + 1
        threefold = repetition_counts[position_key] >= 3
        if halfmove_counter >= 50 or threefold:
            # Canonical ordering matches src/tournament.cpp: a side with no
            # legal move has already lost; only a non-terminal position can be
            # adjudicated drawn by the 25-move or repetition rule.
            if not referee.has_legal_moves():
                outcome = "L" if side_to_move == "W" else "W"
                next_player = white if side_to_move == "W" else black
                return GameResult(
                    outcome, ply, "no legal move from " + next_player.label,
                    moves=moves_log, fens=fens_log)
            reason = "25-move rule" if halfmove_counter >= 50 else "3-fold repetition"
            return GameResult("D", ply, reason,
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
    # --scan-movetime 0.5). See docs/archives/SCAN_METHODOLOGY_GAP.md.
    p.add_argument("--jass-movetime", type=float, default=None,
                   help="per-move time budget (SECONDS) for the Jass side only — "
                        "use with --scan-movetime to NPS-compensate (fair).")
    p.add_argument("--scan-movetime", type=float, default=None,
                   help="per-move time budget (SECONDS) for the Scan side only.")
    p.add_argument("--pairs", type=int, default=2,
                   help="colour-swap pairs per opening (total games = 18 × pairs)")
    p.add_argument("--openings-file", metavar="PATH", default=None,
                   help="play from custom opening FENs (one per line, '#' comments "
                        "stripped) instead of the built-in 9-first-move pool. Used to "
                        "test on a position set, e.g. dilf combination diagrams.")
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
                        "the post-hoc loss-by-piece analyzer for "
                        "diagnostic of where jass wins/loses by piece count.")
    p.add_argument("--jass-threads", type=int, default=1,
                   help="Lazy SMP : number of threads for the jass player "
                        "(via HUB `setoption threads N`). Default "
                        "1. Use with --movetime to see SMP gain — fixed depth "
                        "saturates at the eval ceiling and doesn't surface "
                        "the depth-per-second advantage SMP gives.")
    p.add_argument("--jass-no-book", action="store_true",
                   help="run the jass player with --no-book, so both sides "
                        "play every ply from search. Off by default: Scan has "
                        "been run book=off for a long time while Jass kept its "
                        "built-in book, and every published gate carries that "
                        "asymmetry. Turning this on changes the engine, so it "
                        "must be an explicit protocol choice, not a default.")
    p.add_argument("--jass-search-params", metavar="SPEC", default=None,
                   help="override the jass player's search constants via a "
                        "\"k=v,k=v\" spec (e.g. \"multicut_min_depth=6,"
                        "razor_max_depth=4\") — tune search vs Scan in ONE build, "
                        "no recompile. Keys: src/search_params.hpp.")
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
              "See docs/archives/SCAN_METHODOLOGY_GAP.md.", flush=True)
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

    if getattr(args, "openings_file", None):
        openings = [ln.split("#", 1)[0].strip()
                    for ln in open(args.openings_file)
                    if ln.split("#", 1)[0].strip()]
        print(f"opening pool: {len(openings)} positions (from {args.openings_file})")
    else:
        openings = opening_pool_via_jass(args.jass)
        print(f"opening pool: {len(openings)} positions")
    eval_desc = (f"pattern={args.jass_pattern}" if args.jass_pattern
                 else f"nnue={args.nnue or ('(handcrafted)' if args.no_nnue else '(default)')}")
    jass_book_desc = (args.jass_book if args.jass_book
                      else ("off" if args.jass_no_book else "built-in"))
    print(f"jass setup:   {eval_desc}  book={jass_book_desc}")
    print(f"scan setup:   book={args.scan_book}  bb-size={args.scan_bb_size}")

    jass = JassEngine(args.jass, label="Jass-player",
                      no_nnue=args.no_nnue, nnue_path=args.nnue,
                      pattern_path=args.jass_pattern,
                      book_path=args.jass_book,
                      search_params=args.jass_search_params,
                      threads=args.jass_threads,
                      enforce_no_book=args.jass_no_book)
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
