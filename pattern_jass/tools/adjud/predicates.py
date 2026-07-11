"""v0 adjudication predicates (P2 blockage, P3 trapped-king), composed from
dilf primitives. Each returns a plain bool ("does the predicate fire?"); the
§2 harness scores precision/fire-rate vs TB and only admits >= 99.9%.

Roles (MEMO §1):
  * P3 trapped-king  -> VETO  : suspends the MATERIAL adjudication (zero risk:
    at worst the game continues). Fires when the nominal material edge rests on
    a king that is geometrically dead.
  * P2 blockage      -> DRAW verdict : the position is locked, no side can make
    progress; the ply-cap would otherwise label this by exhaustion.

Conservatism knobs are explicit parameters so the harness can sweep them.
"""

from __future__ import annotations

from dataclasses import replace

from pedagogy.game import GameState, Side
from pedagogy.features.material import count_material, KING_VALUE
from pedagogy.features.mobility import count_legal_moves, threatened_captures
from pedagogy.protocols import EngineProtocol


def ahead_side(state: GameState) -> Side | None:
    """Side with the positive material balance (dame=3), or None if level."""
    bal = count_material(state)["balance"]
    if bal > 0:
        return "white"
    if bal < 0:
        return "black"
    return None


def has_capture(state: GameState, side: Side, engine: EngineProtocol) -> bool:
    """True iff ``side`` has at least one capture available (max-capture rule)."""
    return len(threatened_captures(state, side, engine)) > 0


def _self_move_count(state: GameState, sq: int, side: Side, engine: EngineProtocol) -> int:
    """Number of legal moves originating from square ``sq`` for ``side``."""
    moves = engine.legal_moves(replace(state, turn=side))
    return sum(1 for m in moves if m.from_square == sq)


# ---------------------------------------------------------------------------
# P3 — trapped king (VETO of the material adjudication)
# ---------------------------------------------------------------------------
def p3_trapped_king_veto(
    state: GameState,
    engine: EngineProtocol,
    ahead: Side,
    *,
    margin: int | None = None,
) -> bool:
    """Veto the material WIN call when ``ahead`` owns a geometrically dead king.

    Fires iff, in a position that is QUIET for ``ahead`` (no capture available —
    otherwise the max-capture rule masks a king's quiet moves), at least one of
    ``ahead``'s kings has ZERO legal moves of its own.

    When ``margin`` is given, additionally require the trapped king to be
    load-bearing: discounting its 3-man value drops ``ahead``'s edge BELOW
    ``margin`` (the material-adjud threshold the caller fired at) — i.e. the
    "win" leans on the dead piece. This keeps the veto conservative (higher
    TB-precision). ``margin=None`` = veto on any immobile ahead-king.
    """
    kings = state.kings_of(ahead)
    if not kings:
        return False
    if has_capture(state, ahead, engine):
        return False  # only judge king mobility in a quiet position
    trapped = [k for k in kings if _self_move_count(state, k, ahead, engine) == 0]
    if not trapped:
        return False
    if margin is None:
        return True
    edge_without_one_dead_king = abs(count_material(state)["balance"]) - KING_VALUE
    return edge_without_one_dead_king < margin


# ---------------------------------------------------------------------------
# P2 — total blockage (DRAW verdict)
# ---------------------------------------------------------------------------
def p2_blockage_draw(
    state: GameState,
    engine: EngineProtocol,
    *,
    max_mobility: int = 2,
    allow_kings: bool = False,
) -> bool:
    """Predict DRAW on a locked position.

    Fires iff BOTH sides are quiet (no captures for either) and BOTH sides have
    at most ``max_mobility`` legal moves, and (unless ``allow_kings``) there are
    NO kings on the board (kings unlock almost any structure).
    """
    if not allow_kings and (state.white_kings or state.black_kings):
        return False
    if has_capture(state, "white", engine) or has_capture(state, "black", engine):
        return False
    w = count_legal_moves(state, "white", engine)
    b = count_legal_moves(state, "black", engine)
    return w <= max_mobility and b <= max_mobility
