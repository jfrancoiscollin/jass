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
from pedagogy.features.geometry import promotion_distance, square_to_coords, coords_to_square
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


# ---------------------------------------------------------------------------
# P1 — imprenable breakthrough (runaway) -> WIN verdict
# ---------------------------------------------------------------------------
def _clear_forward_run(state: GameState, m: int, side: Side, d: int) -> int | None:
    """Landing square if ``side``'s man ``m`` has a STRAIGHT diagonal run of ``d``
    empty squares reaching its promotion row (else None). Tries both columns."""
    r, c = square_to_coords(m)
    dr = -1 if side == "white" else 1
    occ = state.all_pieces
    for dc in (-1, 1):
        rr, cc, ok = r, c, True
        for _ in range(d):
            rr += dr; cc += dc
            if not (1 <= rr <= 10 and 1 <= cc <= 10):
                ok = False; break
            try:
                sq = coords_to_square(rr, cc)
            except ValueError:
                ok = False; break
            if sq in occ:
                ok = False; break
        if ok and ((side == "white" and rr == 1) or (side == "black" and rr == 10)):
            return coords_to_square(rr, cc)
    return None


def _man_jumpable(state: GameState, sq: int, by_men: frozenset[int]) -> bool:
    """True iff an opponent *man* in ``by_men`` can jump over ``sq`` in one step
    (attacker diagonally adjacent, empty landing on the opposite side)."""
    r, c = square_to_coords(sq)
    empties = state.empty_squares
    for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        ar, ac = r + dr, c + dc
        lr, lc = r - dr, c - dc
        if not (1 <= ar <= 10 and 1 <= ac <= 10 and 1 <= lr <= 10 and 1 <= lc <= 10):
            continue
        try:
            att = coords_to_square(ar, ac); land = coords_to_square(lr, lc)
        except ValueError:
            continue
        if att in by_men and land in empties:
            return True
    return False


def p1_runaway_win(
    state: GameState,
    engine: EngineProtocol,
    ahead: Side,
    *,
    max_d: int = 3,
) -> bool:
    """Predict WIN for ``ahead`` on an unstoppable promotion (conservative v0).

    Fires iff ``ahead`` has a man with a clear straight diagonal run to promotion
    in ``d <= max_d`` steps, AND the defender: has NO king (kings intercept a
    flying promotion), has NO capture available (else it's tactics, not a race),
    has NO man that can promote as fast (no equal counter-runaway), and cannot
    jump the promotion landing square. ``ahead`` must itself have no pending
    capture (a quiet race). Deliberately strict -> aims for high TB-precision.
    """
    defender: Side = "black" if ahead == "white" else "white"
    if state.kings_of(defender):
        return False
    if threatened_captures(state, defender, engine):
        return False
    if threatened_captures(state, ahead, engine):
        return False
    def_men = state.men_of(defender)
    for m in state.men_of(ahead):
        d = promotion_distance(m, ahead)
        if not (1 <= d <= max_d):
            continue
        land = _clear_forward_run(state, m, ahead, d)
        if land is None:
            continue
        if any(promotion_distance(dm, defender) <= d for dm in def_men):
            continue  # defender promotes as fast -> not clearly winning
        if _man_jumpable(state, land, def_men):
            continue  # promotion square immediately recapturable
        return True
    return False
