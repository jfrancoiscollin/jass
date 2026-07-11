"""dilf EngineProtocol backed by jass ``--dump-legal`` output.

jass emits legal moves in batch (one Hub FEN per input line, moves 1:1 by line
order); this module parses that into ``pedagogy.game.Move`` objects and exposes
a structural :class:`DumpEngine` satisfying dilf's ``EngineProtocol`` (only
``legal_moves`` is consulted by the mobility primitives; ``apply_move`` is not
used by the adjudication predicates and raises).

Token grammar (see src/main.cpp run_dump_legal_mode):
  quiet    "from>to"
  capture  "from>to*c1,c2,..."   (captured squares, FMJD 1..50)
  promotion suffix "+"
  empty line = terminal (no legal move) ; "?" = bad FEN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from pedagogy.game import GameState, Move, state_to_fen


def parse_move_token(tok: str) -> Move:
    """Parse one ``--dump-legal`` move token into a dilf ``Move``."""
    promotion = tok.endswith("+")
    if promotion:
        tok = tok[:-1]
    captures: tuple[int, ...] = ()
    if "*" in tok:
        move_part, cap_part = tok.split("*", 1)
        captures = tuple(int(x) for x in cap_part.split(","))
    else:
        move_part = tok
    frm, to = move_part.split(">", 1)
    return Move(path=(int(frm), int(to)), captures=captures, promotion=promotion)


def parse_dump_line(line: str) -> list[Move]:
    """Parse one output line of ``--dump-legal`` into a list of ``Move``.

    Empty line (terminal) and the bad-FEN marker ``?`` both yield ``[]``.
    """
    line = line.strip()
    if line == "" or line == "?":
        return []
    return [parse_move_token(t) for t in line.split()]


@dataclass
class DumpEngine:
    """EngineProtocol whose ``legal_moves`` is a precomputed FEN -> [Move] table.

    The table is keyed by ``state_to_fen(state)`` so that dilf's turn-flipped
    mobility queries resolve — the caller MUST have dumped both turn variants of
    every sampled position (``turn="white"`` and ``turn="black"``).
    """

    table: dict[str, list[Move]] = field(default_factory=dict)

    def legal_moves(self, state: GameState) -> Sequence[Move]:
        key = state_to_fen(state)
        moves = self.table.get(key)
        if moves is None:
            raise KeyError(f"no --dump-legal entry for {key!r}")
        return moves

    def apply_move(self, state: GameState, move: Move) -> GameState:  # pragma: no cover
        raise NotImplementedError("DumpEngine does not apply moves")

    def add(self, fen: str, line: str) -> None:
        """Register a dumped line for the FEN it was generated from."""
        self.table[fen] = parse_dump_line(line)
