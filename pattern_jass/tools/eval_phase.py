"""Dependency-light phase helpers shared by the streaming fit and diagnostics."""

from __future__ import annotations

import numpy as np


def _tempo_weights() -> tuple[np.ndarray, np.ndarray]:
    white = np.zeros(64, dtype=np.float64)
    black = np.zeros(64, dtype=np.float64)
    for index in range(64):
        bit = (index // 8) * 8 + (7 - index % 8)
        if bit < 50:
            row = bit // 5
            white[index] = row
            black[index] = 9 - row
    return white, black


TEMPO_WHITE_WEIGHTS, TEMPO_BLACK_WEIGHTS = _tempo_weights()


def piece_count_bb(wm, wk, bm, bk) -> np.ndarray:
    """Total pieces per packed bitboard row."""
    occupied = wm | wk | bm | bk
    bits = np.unpackbits(occupied.view(np.uint8)).reshape(len(occupied), 64)
    return bits.sum(axis=1)


def tempo_wmg_bb(wm, bm) -> np.ndarray:
    """Scan tempo midgame weight, identical to the streaming fit path."""
    white = np.unpackbits(wm.view(np.uint8)).reshape(len(wm), 64).astype(np.float64)
    black = np.unpackbits(bm.view(np.uint8)).reshape(len(bm), 64).astype(np.float64)
    tempo = white.dot(TEMPO_WHITE_WEIGHTS) + black.dot(TEMPO_BLACK_WEIGHTS)
    return np.clip(tempo / 300.0, 0.0, 1.0)
