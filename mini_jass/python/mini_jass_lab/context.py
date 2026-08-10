"""Deterministic L1 contextual features with an explicit rules boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

import numpy as np

BOARD_SIZE = 5
PLAYABLE_SQUARES = 13
MAX_PIECES_PER_SIDE = 2
REVERSIBLE_PLY_LIMIT = 20
MAX_LEGAL_MOVES = 8
MAX_CAPTURE_MOVES = 4
WHITE = 0
BLACK = 1
ONGOING = 0
SIDE_TO_MOVE_LOSS = 1
DRAW = 2

SQUARE_COORDINATES: tuple[tuple[int, int], ...] = (
    (0, 0),
    (0, 2),
    (0, 4),
    (1, 1),
    (1, 3),
    (2, 0),
    (2, 2),
    (2, 4),
    (3, 1),
    (3, 3),
    (4, 0),
    (4, 2),
    (4, 4),
)
SQUARE_AT = {coordinate: square for square, coordinate in enumerate(SQUARE_COORDINATES)}
SQUARE_ROT180: tuple[int, ...] = tuple(
    SQUARE_AT[(BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - column)]
    for row, column in SQUARE_COORDINATES
)
WHITE_PROMOTION_ROW = 0
BLACK_PROMOTION_ROW = BOARD_SIZE - 1
CENTER_SQUARES: tuple[int, ...] = tuple(
    square
    for square, (row, column) in enumerate(SQUARE_COORDINATES)
    if 1 <= row <= 3 and 1 <= column <= 3
)

COMPONENTS: tuple[str, ...] = (
    "material_man_delta",
    "material_king_delta",
    "legal_move_delta",
    "capture_option_delta",
    "promotion_pressure_delta",
    "blocked_man_delta",
    "advanced_man_delta",
    "center_presence_delta",
    "terminal_flag",
)


@dataclass(frozen=True)
class ContextState:
    white_men: int
    black_men: int
    white_kings: int
    black_kings: int
    side_to_move: int
    reversible_plies: int

    @property
    def occupied(self) -> int:
        return self.white_men | self.black_men | self.white_kings | self.black_kings


def state_from_oracle(oracle: object, state_id: int) -> ContextState:
    boards = np.asarray(getattr(oracle, "bitboards"))[state_id]
    return ContextState(
        *(int(value) for value in boards),
        int(np.asarray(getattr(oracle, "sides"))[state_id]),
        int(np.asarray(getattr(oracle, "reversible_plies"))[state_id]),
    )


def _bits(bits: int) -> Iterable[int]:
    for square in range(PLAYABLE_SQUARES):
        if bits & (1 << square):
            yield square


def _pieces(state: ContextState, side: int) -> tuple[int, int]:
    if side == WHITE:
        return state.white_men, state.white_kings
    if side == BLACK:
        return state.black_men, state.black_kings
    raise ValueError("side must be exactly zero or one")


def _opponent_bits(state: ContextState, side: int) -> int:
    men, kings = _pieces(state, 1 - side)
    return men | kings


def _capture_paths(
    *,
    origin: int,
    current: int,
    stationary_own: int,
    opponent: int,
    landings: tuple[int, ...] = (),
) -> list[tuple[int, tuple[int, ...]]]:
    row, column = SQUARE_COORDINATES[current]
    occupied = stationary_own | opponent | (1 << current)
    paths: list[tuple[int, tuple[int, ...]]] = []
    extended = False
    for row_delta in (-2, 2):
        for column_delta in (-2, 2):
            landing = SQUARE_AT.get((row + row_delta, column + column_delta))
            captured = SQUARE_AT.get((row + row_delta // 2, column + column_delta // 2))
            if landing is None or captured is None:
                continue
            if not opponent & (1 << captured) or occupied & (1 << landing):
                continue
            if len(landings) >= MAX_PIECES_PER_SIDE:
                raise ValueError("capture sequence exceeds the L1 material bound")
            paths.extend(
                _capture_paths(
                    origin=origin,
                    current=landing,
                    stationary_own=stationary_own,
                    opponent=opponent & ~(1 << captured),
                    landings=(*landings, landing),
                )
            )
            extended = True
    if not extended and landings:
        paths.append((origin, landings))
    return paths


def board_moves(
    state: ContextState, side: int | None = None
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Return the exact L1 complete moves before the reversible-draw rule."""
    queried = state.side_to_move if side is None else int(side)
    men, kings = _pieces(state, queried)
    own = men | kings
    opponent = _opponent_bits(state, queried)
    captures: list[tuple[int, tuple[int, ...]]] = []
    for origin in _bits(own):
        captures.extend(
            _capture_paths(
                origin=origin,
                current=origin,
                stationary_own=own & ~(1 << origin),
                opponent=opponent,
            )
        )
    if captures:
        return tuple(sorted(set(captures)))

    moves: list[tuple[int, tuple[int, ...]]] = []
    occupied = state.occupied
    for origin in _bits(own):
        row, column = SQUARE_COORDINATES[origin]
        row_deltas = (
            (-1, 1) if kings & (1 << origin) else ((-1,) if queried == WHITE else (1,))
        )
        for row_delta in row_deltas:
            for column_delta in (-1, 1):
                destination = SQUARE_AT.get((row + row_delta, column + column_delta))
                if destination is not None and not occupied & (1 << destination):
                    moves.append((origin, (destination,)))
    return tuple(sorted(moves))


def legal_moves(
    state: ContextState, side: int | None = None
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Return exact legal moves, including the reversible-ply terminal rule."""
    moves = board_moves(state, side)
    if not moves or state.reversible_plies >= REVERSIBLE_PLY_LIMIT:
        return ()
    return moves


def terminal_status(state: ContextState) -> int:
    if not board_moves(state, state.side_to_move):
        return SIDE_TO_MOVE_LOSS
    if state.reversible_plies >= REVERSIBLE_PLY_LIMIT:
        return DRAW
    return ONGOING


def _capture_count(moves: tuple[tuple[int, tuple[int, ...]], ...]) -> int:
    count = 0
    for origin, landings in moves:
        row, column = SQUARE_COORDINATES[origin]
        target_row, target_column = SQUARE_COORDINATES[landings[0]]
        if abs(row - target_row) == 2 and abs(column - target_column) == 2:
            count += 1
    return count


def _blocked_men(state: ContextState, side: int) -> int:
    men, _ = _pieces(state, side)
    forward = -1 if side == WHITE else 1
    blocked = 0
    for square in _bits(men):
        row, column = SQUARE_COORDINATES[square]
        destinations = (
            SQUARE_AT.get((row + forward, column - 1)),
            SQUARE_AT.get((row + forward, column + 1)),
        )
        if not any(
            target is not None and not state.occupied & (1 << target)
            for target in destinations
        ):
            blocked += 1
    return blocked


def _promotion_pressure(state: ContextState, side: int) -> float:
    men, _ = _pieces(state, side)
    total = 0.0
    for square in _bits(men):
        row = SQUARE_COORDINATES[square][0]
        progress = (BOARD_SIZE - 1 - row) if side == WHITE else row
        total += progress / (BOARD_SIZE - 1)
    return total / MAX_PIECES_PER_SIDE


def _advanced_men(state: ContextState, side: int) -> int:
    men, _ = _pieces(state, side)
    advanced = 0
    for square in _bits(men):
        row = SQUARE_COORDINATES[square][0]
        progress = BOARD_SIZE - 1 - row if side == WHITE else row
        if progress > (BOARD_SIZE - 1) / 2:
            advanced += 1
    return advanced


def _center_count(state: ContextState, side: int) -> int:
    men, kings = _pieces(state, side)
    occupied = men | kings
    return sum(bool(occupied & (1 << square)) for square in CENTER_SQUARES)


def context_vector(state: ContextState, pov: int | None = None) -> np.ndarray:
    """Return context from ``pov``; default POV is the side to move."""
    own = state.side_to_move if pov is None else int(pov)
    if own not in (WHITE, BLACK):
        raise ValueError("POV must be exactly zero or one")
    opponent = 1 - own
    own_men, own_kings = _pieces(state, own)
    other_men, other_kings = _pieces(state, opponent)
    own_moves = legal_moves(state, own)
    other_moves = legal_moves(state, opponent)
    status = terminal_status(state)
    terminal = 0.0
    if status == SIDE_TO_MOVE_LOSS:
        terminal = -1.0 if own == state.side_to_move else 1.0
    result = np.asarray(
        (
            (own_men.bit_count() - other_men.bit_count()) / MAX_PIECES_PER_SIDE,
            (own_kings.bit_count() - other_kings.bit_count()) / MAX_PIECES_PER_SIDE,
            (len(own_moves) - len(other_moves)) / MAX_LEGAL_MOVES,
            (_capture_count(own_moves) - _capture_count(other_moves))
            / MAX_CAPTURE_MOVES,
            _promotion_pressure(state, own) - _promotion_pressure(state, opponent),
            (_blocked_men(state, own) - _blocked_men(state, opponent))
            / MAX_PIECES_PER_SIDE,
            (_advanced_men(state, own) - _advanced_men(state, opponent))
            / MAX_PIECES_PER_SIDE,
            (_center_count(state, own) - _center_count(state, opponent))
            / MAX_PIECES_PER_SIDE,
            terminal,
        ),
        dtype=np.float64,
    )
    if not np.all(np.isfinite(result)) or np.any(np.abs(result) > 1.0):
        raise ValueError("context feature left its frozen finite range")
    return result


def context_matrix(
    oracle: object,
    state_ids: Iterable[int],
    pov_sides: Iterable[int] | None = None,
) -> np.ndarray:
    ids = tuple(int(value) for value in state_ids)
    if pov_sides is None:
        sides = (None,) * len(ids)
    else:
        sides = tuple(int(value) for value in pov_sides)
        if len(sides) != len(ids):
            raise ValueError("POV side count must match state count")
    rows = [
        context_vector(state_from_oracle(oracle, state_id), side)
        for state_id, side in zip(ids, sides)
    ]
    return np.asarray(rows, dtype=np.float64)


def rotate180_and_swap_colours(state: ContextState) -> ContextState:
    def rotate(bits: int) -> int:
        result = 0
        for source in _bits(bits):
            result |= 1 << SQUARE_ROT180[source]
        return result

    return ContextState(
        white_men=rotate(state.black_men),
        black_men=rotate(state.white_men),
        white_kings=rotate(state.black_kings),
        black_kings=rotate(state.white_kings),
        side_to_move=1 - state.side_to_move,
        reversible_plies=state.reversible_plies,
    )


def feature_definition() -> dict[str, object]:
    return {
        "schema": "mini_jass.context_features.v1",
        "components": list(COMPONENTS),
        "board_size": BOARD_SIZE,
        "playable_squares": PLAYABLE_SQUARES,
        "square_coordinates": [list(value) for value in SQUARE_COORDINATES],
        "rot180_square_map": list(SQUARE_ROT180),
        "center_squares": list(CENTER_SQUARES),
        "maximum_pieces_per_side": MAX_PIECES_PER_SIDE,
        "legal_move_normalizer": MAX_LEGAL_MOVES,
        "capture_option_normalizer": MAX_CAPTURE_MOVES,
        "promotion_pressure_denominator": BOARD_SIZE - 1,
        "advanced_man_progress_strictly_greater_than": (BOARD_SIZE - 1) / 2,
        "terminal_flag": "exact_outcome_from_requested_pov_loss_minus1_win_plus1_else0",
        "mobility": "exact_mandatory_capture_moves_with_reversible_terminal_rule",
    }


def feature_definition_hash() -> str:
    payload = json.dumps(
        feature_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
