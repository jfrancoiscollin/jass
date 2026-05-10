#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Train a Jass `LinearNetwork` from a self-play dataset.

Pipeline
--------
    ./build/jass --gen-data 1000000 selfplay.bin
    python3 tools/train.py --data selfplay.bin --out nnue.bin

The output `nnue.bin` is the binary format consumed by
`LinearNetwork::load(path)` in src/nnue.cpp: 200 little-endian int32
weights, indexed by (square 0..49, piece-kind 0..3) in square-major
order — the same layout `LinearNetwork::save()` writes when called
from C++.

Architecture
------------
This is a *linear* model (no hidden layer).  It mirrors the
`LinearNetwork` used at runtime, so its strength matches the
handcrafted eval modulo the support-bonus runtime term.  To upgrade to
an MLP, replace `LinearTrainer` with a PyTorch `nn.Module`; the
binary format will need extending in lockstep with `LinearNetwork`.

Input format
------------
The dataset file `selfplay.bin` written by `--gen-data` is:

    Header (8 bytes)
        4 bytes  magic = "JNNT"
        4 bytes  uint32 record_count

    Each record (37 bytes)
        8 bytes  uint64  white_men   bitboard
        8 bytes  uint64  white_kings bitboard
        8 bytes  uint64  black_men   bitboard
        8 bytes  uint64  black_kings bitboard
        1 byte   uint8   side_to_move   (0 = white, 1 = black)
        4 bytes  int32   target_score   (centipawns, side-to-move POV)

NumPy is enough for the linear case (closed-form least squares) and is
the only required runtime dependency.  PyTorch is optional and only
useful when extending to a non-linear network.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

NUM_SQUARES = 50
NUM_KINDS   = 4   # 0=white-man, 1=white-king, 2=black-man, 3=black-king
NUM_FEATS   = NUM_SQUARES * NUM_KINDS  # 200

# Must match the C++ side.
TEMPO_BONUS = 5

MAGIC = b"JNNT"
RECORD_SIZE = 37


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (X, y) where X is (N, 200) float32 and y is (N,) float32.

    `y` is the target score in *white-POV*, with the constant tempo
    bonus already subtracted, so the model learns the per-piece
    contributions directly.  Adding the tempo back is the engine's
    job at evaluate time.
    """
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: bad magic — is this a Jass NNUE dataset?")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected_size = 8 + count * RECORD_SIZE
    if len(raw) != expected_size:
        raise ValueError(
            f"{path}: expected {expected_size} bytes "
            f"(8 header + {count}×{RECORD_SIZE}), got {len(raw)}"
        )

    X = np.zeros((count, NUM_FEATS), dtype=np.float32)
    y = np.zeros(count,             dtype=np.float32)

    for i in range(count):
        off = 8 + i * RECORD_SIZE
        wm, wk, bm, bk = struct.unpack_from("<QQQQ", raw, off)
        stm   = raw[off + 32]
        score = struct.unpack_from("<i", raw, off + 33)[0]

        # Build the binary feature vector for this position.
        for sq in range(NUM_SQUARES):
            bit = 1 << sq
            if wm & bit: X[i, sq * NUM_KINDS + 0] = 1.0
            if wk & bit: X[i, sq * NUM_KINDS + 1] = 1.0
            if bm & bit: X[i, sq * NUM_KINDS + 2] = 1.0
            if bk & bit: X[i, sq * NUM_KINDS + 3] = 1.0

        # Convert STM-POV target to white-POV pre-tempo.
        if stm == 0:
            target_white = score - TEMPO_BONUS
        else:
            target_white = -score - (-TEMPO_BONUS)
            # which simplifies to:  -score + TEMPO_BONUS
        y[i] = target_white

    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def fit_linear(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Closed-form least-squares fit of a 200-coefficient linear model.

    Mate-like targets (very large magnitudes) are clipped so a single
    decisive game doesn't dominate the loss.
    """
    clip = 2000  # ~20 men of material; everything beyond is treated as ±20 men
    y_clipped = np.clip(y, -clip, clip).astype(np.float32)

    # `lstsq` is exact for a linear model and runs in O(N · F²).  For
    # F=200 features and N up to a few million it stays well under a
    # second on a desktop CPU.
    weights, *_ = np.linalg.lstsq(X, y_clipped, rcond=None)
    return weights.astype(np.float32)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def save_weights(weights: np.ndarray, path: Path) -> None:
    """Write `weights` in the format `LinearNetwork::load` expects."""
    if weights.shape != (NUM_FEATS,):
        raise ValueError(f"weights shape {weights.shape} != ({NUM_FEATS},)")
    rounded = np.round(weights).astype(np.int32, copy=False)
    rounded.tofile(path)


def report(weights: np.ndarray) -> None:
    """Print a small summary so the user can sanity-check the run."""
    rounded = np.round(weights).astype(np.int32)
    print(f"weights summary: min={rounded.min()} max={rounded.max()} "
          f"mean={float(rounded.mean()):+.1f} std={float(rounded.std()):.1f}")
    # Per-kind average.
    by_kind = rounded.reshape(NUM_SQUARES, NUM_KINDS).mean(axis=0)
    labels = ["white-man", "white-king", "black-man", "black-king"]
    for label, val in zip(labels, by_kind):
        print(f"  mean({label:10s}) = {val:+7.1f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Train a Jass LinearNetwork from a self-play dataset.")
    parser.add_argument("--data", type=Path, required=True,
                        help="path to the dataset produced by --gen-data")
    parser.add_argument("--out",  type=Path, default=Path("nnue.bin"),
                        help="output weights file (default: nnue.bin)")
    args = parser.parse_args(argv)

    print(f"loading {args.data} …")
    X, y = load_dataset(args.data)
    print(f"  {X.shape[0]} records, {X.shape[1]} features")

    print("fitting linear model …")
    weights = fit_linear(X, y)
    report(weights)

    save_weights(weights, args.out)
    print(f"wrote weights to {args.out} "
          f"({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
