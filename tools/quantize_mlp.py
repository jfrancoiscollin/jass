#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Post-training int8 quantisation of a Jass MLP.

Pipeline
--------
    # 1) Train float32 weights (any of 64-32, 128-64, 256-128, 512-256 etc.).
    python3 tools/train_v3.py --data selfplay-wdl.bin \
        --archs 256-128 --epochs 30 --out-dir trained_v3

    # 2) Quantise to int8 using the same dataset for calibration.
    python3 tools/quantize_mlp.py \
        --in trained_v3/nnue-256-128.bin \
        --data selfplay-wdl.bin \
        --out nnue-256-128-q.bin

`mlp-q.bin` follows the JNNQ format consumed by `MLPNetworkQ::load()`
in src/nnue.cpp. The header now carries the runtime hidden dims (any
multiple of 32) since Cycle 4a:

    [0..4)   magic = "JNNQ"
    [4..8)   uint32 version (currently 1)
    [8..12)  uint32 input_dim   (must equal 200)
    [12..16) uint32 hidden1     (multiple of 32, ≤ 1024)
    [16..20) uint32 hidden2     (multiple of 32, ≤ 1024)
    [20..24) uint32 output_dim  (must equal 1)
    [24..28) float32 mul1     (acc1 → int8 h1 factor)
    [28..32) float32 mul2     (acc2 → int8 h2 factor)
    [32..36) float32 mul_out  (acc3 → centipawn)
    [36..)   weights:
              w1 [hidden1 × INPUT_DIM]   int8
              b1 [hidden1]               int32 (at acc1 scale = sw1)
              w2 [hidden2 × hidden1]     int8
              b2 [hidden2]               int32 (at acc2 scale = sw2 · sh1)
              w3 [hidden2]               int8
              b3                         int32 (at acc3 scale = sw3 · sh2)

Quantisation scheme
-------------------
Symmetric per-tensor: q = round(W / s) where s = max(|W|) / 127.

Three "passes" between layers carry the inter-quantum scale:

    mul1    = sw1 / sh1       (acc1 → h1, both pre-ReLU and post-quant)
    mul2    = (sw2 · sh1) / sh2
    mul_out = sw3 · sh2

Activation scales `sh1` and `sh2` are calibrated by running the
float32 network on a small slice of the training set and taking the
99.9th percentile of ReLU outputs per layer (robust to outliers).

The output magnitude can exceed int8 range (we want centipawn scores
up to ~29000), so the final `mul_out` returns a float directly that
gets cast to int.

Calibration data
----------------
The script auto-detects the dataset magic:
  * JNNW (38 bytes/record, post-Cycle-1 self-play) — preferred
  * JNNT (37 bytes/record, legacy) — still supported
Only the 32-byte bitboard + 1-byte STM prefix is needed for
calibration; the score/WDL tail is ignored.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

# Must stay in lockstep with src/nnue.hpp (MLPNetwork + MLPNetworkQ).
NUM_SQUARES        = 50
NUM_KINDS          = 4
NUM_FEATS_V2       = NUM_SQUARES * NUM_KINDS       # 200, V2 dense
NUM_FEATS_HALFMEN  = 200 + 200 + 50                # 450, HalfMen lite
NUM_FEATS          = NUM_FEATS_V2  # legacy alias
MAX_HIDDEN         = 1024
SIMD_TILE          = 32

JNNM_MAGIC      = b"JNNM"
JNNM_VERSION_V2 = 2
JNNM_VERSION_V3 = 3  # adds HalfMen input encoding

JNNQ_MAGIC      = b"JNNQ"
JNNQ_VERSION_V1 = 1
JNNQ_VERSION_V2 = 2  # adds HalfMen input encoding
JNNQ_VERSION    = JNNQ_VERSION_V2  # version emitted by save_jnnq

# Calibration dataset formats. Only the 32-byte bitboard + 1-byte STM
# prefix matters here; the rest of the record is ignored.
DATASET_JNNT_MAGIC     = b"JNNT"
DATASET_JNNT_RECORD_SZ = 37
DATASET_JNNW_MAGIC     = b"JNNW"
DATASET_JNNW_RECORD_SZ = 38


# ---------------------------------------------------------------------------
# Load the float32 JNNM file produced by train_v3.py / train_mlp.py
# ---------------------------------------------------------------------------
def load_jnnm(path: Path):
    """Returns (w1, b1, w2, b2, w3, b3, input_dim, hidden1, hidden2).

    Accepts JNNM v2 (input_dim must be 200) and JNNM v3 (input_dim in
    {200, 450}). v2 is kept for backward compat with files written
    before Cycle 6c; new outputs from train_v3.py are v3."""
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:4] != JNNM_MAGIC:
        raise ValueError(f"{path}: bad magic — not a JNNM file?")
    version, in_dim, h1, h2, out_dim = struct.unpack_from("<IIIII", raw, 4)

    if version == JNNM_VERSION_V2:
        if in_dim != NUM_FEATS_V2:
            raise ValueError(
                f"{path}: v2 must have input_dim={NUM_FEATS_V2}, got {in_dim}")
    elif version == JNNM_VERSION_V3:
        if in_dim not in (NUM_FEATS_V2, NUM_FEATS_HALFMEN):
            raise ValueError(
                f"{path}: v3 input_dim must be {NUM_FEATS_V2} or "
                f"{NUM_FEATS_HALFMEN}, got {in_dim}")
    else:
        raise ValueError(f"{path}: unsupported JNNM version {version}")

    if out_dim != 1:
        raise ValueError(f"{path}: output_dim={out_dim} (expected 1)")
    if h1 == 0 or h1 > MAX_HIDDEN or h2 == 0 or h2 > MAX_HIDDEN:
        raise ValueError(f"{path}: hidden dims out of range: {h1}, {h2}")
    if h1 % SIMD_TILE != 0 or h2 % SIMD_TILE != 0:
        raise ValueError(
            f"{path}: hidden dims ({h1}, {h2}) must be multiples of "
            f"{SIMD_TILE} so the JNNQ output is loadable by the C++ side")

    off = 24
    def take(n: int) -> np.ndarray:
        nonlocal off
        arr = np.frombuffer(raw, dtype=np.float32, count=n, offset=off).copy()
        off += n * 4
        return arr

    w1 = take(h1 * in_dim).reshape(h1, in_dim)
    b1 = take(h1)
    w2 = take(h2 * h1).reshape(h2, h1)
    b2 = take(h2)
    w3 = take(h2)
    b3 = float(np.frombuffer(raw, dtype=np.float32, count=1, offset=off)[0])
    return w1, b1, w2, b2, w3, b3, in_dim, h1, h2


# ---------------------------------------------------------------------------
# Build the STM-relative feature matrix for a calibration slice.
# ---------------------------------------------------------------------------
def _encode_v2(bbs: np.ndarray, stm: np.ndarray) -> np.ndarray:
    """Dense 200-feature STM-POV encoding, identical to
    train_v3.py::_encode_v2 and src/nnue.cpp accumulate_kind."""
    n = len(stm)
    X = np.zeros((n, NUM_FEATS_V2), dtype=np.float32)
    is_w = (stm == 0)
    is_b = ~is_w
    if is_w.any():
        idx = np.where(is_w)[0]
        sub = bbs[is_w]
        for kind, src in enumerate((0, 1, 2, 3)):
            for sq in range(NUM_SQUARES):
                bit = np.uint64(1) << np.uint64(sq)
                X[idx, sq * NUM_KINDS + kind] = (
                    (sub[:, src] & bit) > 0).astype(np.float32)
    if is_b.any():
        idx = np.where(is_b)[0]
        sub = bbs[is_b]
        for kind, src in enumerate((2, 3, 0, 1)):
            for sq in range(NUM_SQUARES):
                bit = np.uint64(1) << np.uint64(sq)
                X[idx, (NUM_SQUARES - 1 - sq) * NUM_KINDS + kind] = (
                    (sub[:, src] & bit) > 0).astype(np.float32)
    return X


def _find_anchors(bbs: np.ndarray, stm: np.ndarray) -> np.ndarray:
    """Same anchor definition as train_v3.py / src/nnue.cpp."""
    n = len(stm)
    anchors = np.empty(n, dtype=np.int32)
    for i in range(n):
        if stm[i] == 0:
            bb = int(bbs[i, 0]) | int(bbs[i, 1])
            anchors[i] = (bb.bit_length() - 1) if bb else 49
        else:
            bb = int(bbs[i, 2]) | int(bbs[i, 3])
            if bb == 0:
                anchors[i] = 49
            else:
                lsb = (bb & -bb).bit_length() - 1
                anchors[i] = 49 - lsb
    return anchors


def _encode_halfmen(bbs: np.ndarray, stm: np.ndarray) -> np.ndarray:
    """HalfMen lite 450-feature encoding."""
    n = len(stm)
    X = np.zeros((n, NUM_FEATS_HALFMEN), dtype=np.float32)
    X_v2 = _encode_v2(bbs, stm)
    X[:, :200] = X_v2
    anchors = _find_anchors(bbs, stm)
    X[np.arange(n), 400 + anchors] = 1.0
    for kind in range(NUM_KINDS):
        col_idx = np.arange(NUM_SQUARES) * NUM_KINDS + kind
        sub = X_v2[:, col_idx]
        for sq in range(NUM_SQUARES):
            mask = sub[:, sq] > 0
            if not mask.any():
                continue
            rel = (sq - anchors[mask]) % NUM_SQUARES
            X[np.where(mask)[0], 200 + rel * NUM_KINDS + kind] = 1.0
    return X


def load_calibration(path: Path, n_calib: int, input_dim: int) -> np.ndarray:
    """Build the calibration feature matrix with the encoding implied
    by `input_dim` (200 → V2 dense, 450 → HalfMen lite)."""
    raw = path.read_bytes()
    if len(raw) < 8:
        raise ValueError(f"{path}: file too short")
    magic = raw[:4]
    if magic == DATASET_JNNW_MAGIC:
        record_sz = DATASET_JNNW_RECORD_SZ
    elif magic == DATASET_JNNT_MAGIC:
        record_sz = DATASET_JNNT_RECORD_SZ
    else:
        raise ValueError(f"{path}: unknown dataset magic {magic!r}")

    count = struct.unpack_from("<I", raw, 4)[0]
    if 8 + count * record_sz != len(raw):
        raise ValueError(
            f"{path}: size {len(raw)} != header-implied "
            f"{8 + count * record_sz}")
    n_use = min(n_calib, count)
    body  = np.frombuffer(raw[8:8 + n_use * record_sz],
                          dtype=np.uint8).reshape(n_use, record_sz)
    bbs   = body[:, :32].view(np.uint64).reshape(n_use, 4)
    stm   = body[:, 32]

    if input_dim == NUM_FEATS_V2:
        return _encode_v2(bbs, stm)
    if input_dim == NUM_FEATS_HALFMEN:
        return _encode_halfmen(bbs, stm)
    raise ValueError(f"unsupported input_dim {input_dim}")


# ---------------------------------------------------------------------------
# Quantisation
# ---------------------------------------------------------------------------
def quantise(w1, b1, w2, b2, w3, b3, X_calib):
    """Compute int8 weights, int32 biases and the three inter-layer
    multipliers from the float32 reference and a calibration slice."""
    # Weight scales: symmetric, max-abs / 127.
    sw1 = max(np.abs(w1).max(), 1e-8) / 127.0
    sw2 = max(np.abs(w2).max(), 1e-8) / 127.0
    sw3 = max(np.abs(w3).max(), 1e-8) / 127.0

    # Run the float reference on the calibration slice to size sh1/sh2.
    h1_pre = X_calib @ w1.T + b1            # (N, hidden1)
    h1     = np.maximum(0.0, h1_pre)
    h2_pre = h1 @ w2.T + b2                  # (N, hidden2)
    h2     = np.maximum(0.0, h2_pre)

    # 99.9-percentile to be robust to a single outlier.
    sh1 = max(np.percentile(h1, 99.9), 1e-8) / 127.0
    sh2 = max(np.percentile(h2, 99.9), 1e-8) / 127.0

    # Quantise weights.
    w1_q = np.round(w1 / sw1).clip(-127, 127).astype(np.int8)
    w2_q = np.round(w2 / sw2).clip(-127, 127).astype(np.int8)
    w3_q = np.round(w3 / sw3).clip(-127, 127).astype(np.int8)

    # Quantise biases at the accumulator scale.
    b1_q = np.round(b1 / sw1).astype(np.int32)               # acc1 = sw1
    b2_q = np.round(b2 / (sw2 * sh1)).astype(np.int32)        # acc2 = sw2·sh1
    b3_q = int(round(b3 / (sw3 * sh2)))                       # acc3 = sw3·sh2

    mul1    = float(sw1 / sh1)
    mul2    = float((sw2 * sh1) / sh2)
    mul_out = float(sw3 * sh2)

    return (w1_q, b1_q, w2_q, b2_q, w3_q, b3_q,
            mul1, mul2, mul_out,
            dict(sw1=sw1, sw2=sw2, sw3=sw3, sh1=sh1, sh2=sh2))


def quant_eval(X: np.ndarray, q: tuple) -> np.ndarray:
    """Reproduce MLPNetworkQ::evaluate in NumPy for one calibration
    batch — sanity check that the quantised math matches what the
    C++ side will compute."""
    (w1_q, b1_q, w2_q, b2_q, w3_q, b3_q,
     mul1, mul2, mul_out, _) = q
    acc1 = (X.astype(np.int32) @ w1_q.T.astype(np.int32)) + b1_q
    h1   = np.clip(np.round(acc1.astype(np.float32) * mul1), 0, 127).astype(np.int32)
    acc2 = (h1 @ w2_q.T.astype(np.int32)) + b2_q
    h2   = np.clip(np.round(acc2.astype(np.float32) * mul2), 0, 127).astype(np.int32)
    acc3 = (h2 @ w3_q.astype(np.int32)) + b3_q
    return acc3.astype(np.float32) * mul_out


def float_eval(X: np.ndarray, w1, b1, w2, b2, w3, b3) -> np.ndarray:
    h1 = np.maximum(0.0, X @ w1.T + b1)
    h2 = np.maximum(0.0, h1 @ w2.T + b2)
    return h2 @ w3 + b3


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def save_jnnq(path: Path, q: tuple,
              input_dim: int, hidden1: int, hidden2: int) -> None:
    (w1_q, b1_q, w2_q, b2_q, w3_q, b3_q,
     mul1, mul2, mul_out, _) = q
    if w1_q.shape != (hidden1, input_dim):
        raise ValueError(f"w1 shape {w1_q.shape} != ({hidden1}, {input_dim})")
    if w2_q.shape != (hidden2, hidden1):
        raise ValueError(f"w2 shape {w2_q.shape} != ({hidden2}, {hidden1})")
    with path.open("wb") as f:
        f.write(JNNQ_MAGIC)
        f.write(struct.pack("<IIIII",
                            JNNQ_VERSION, input_dim, hidden1, hidden2, 1))
        f.write(struct.pack("<fff", mul1, mul2, mul_out))
        f.write(w1_q.tobytes())
        f.write(b1_q.tobytes())
        f.write(w2_q.tobytes())
        f.write(b2_q.tobytes())
        f.write(w3_q.tobytes())
        f.write(struct.pack("<i", b3_q))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Post-training int8 quantisation of a Jass MLP.")
    p.add_argument("--in",     dest="in_path",  type=Path, required=True,
                   help="float32 JNNM file from train_v3.py / train_mlp.py")
    p.add_argument("--data",   type=Path,       required=True,
                   help="self-play dataset for activation calibration "
                        "(JNNW or legacy JNNT)")
    p.add_argument("--out",    type=Path,       default=Path("nnue-q.bin"),
                   help="output JNNQ file (default: nnue-q.bin)")
    p.add_argument("--n-calib", type=int,       default=2000,
                   help="number of calibration positions (default: 2000)")
    args = p.parse_args(argv)

    print(f"loading float reference {args.in_path} …")
    w1, b1, w2, b2, w3, b3, input_dim, hidden1, hidden2 = load_jnnm(args.in_path)
    encoding = "halfmen" if input_dim == NUM_FEATS_HALFMEN else "v2"
    print(f"  topology: {input_dim} → {hidden1} → {hidden2} → 1  "
          f"(encoding={encoding})")

    print(f"loading {args.n_calib} calibration positions from {args.data} …")
    X_calib = load_calibration(args.data, args.n_calib, input_dim=input_dim)
    print(f"  {X_calib.shape[0]} positions, feature dim {X_calib.shape[1]}")

    print("quantising …")
    q = quantise(w1, b1, w2, b2, w3, b3, X_calib)
    (_, _, _, _, _, _, mul1, mul2, mul_out, scales) = q
    print(f"  scales: sw1={scales['sw1']:.5g} sw2={scales['sw2']:.5g} "
          f"sw3={scales['sw3']:.5g} sh1={scales['sh1']:.5g} sh2={scales['sh2']:.5g}")
    print(f"  multipliers: mul1={mul1:.5g} mul2={mul2:.5g} mul_out={mul_out:.5g}")

    # Sanity: compare the quantised network's output to the float reference
    # on the calibration slice. Use the Python int math (mirrors the C++).
    float_out = float_eval(X_calib, w1, b1, w2, b2, w3, b3)
    quant_out = quant_eval(X_calib, q)
    diff      = float_out - quant_out
    print(f"  reference range: float [{float_out.min():.1f}, {float_out.max():.1f}], "
          f"quantised [{quant_out.min():.1f}, {quant_out.max():.1f}]")
    print(f"  diff: mean={diff.mean():+.2f}  std={diff.std():.2f}  "
          f"|max|={np.abs(diff).max():.2f}  RMSE={np.sqrt((diff**2).mean()):.2f}")

    save_jnnq(args.out, q, input_dim, hidden1, hidden2)
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
