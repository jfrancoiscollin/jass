#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Exploratory scout: does a HalfKP-style anchor-relative input encoding
beat the v2 flat 200-feature encoding on the same training data?

Trains two MLPs back-to-back on the same dataset:

  v2 baseline   (200 features)
    feat[piece_sq * 4 + kind]                   absolute square × kind
    Same as production tools/train_v3.py.

  HalfMen lite  (450 features)
    feat[piece_sq * 4 + kind]                   absolute (kept)
    feat[200 + ((piece_sq - anchor) % 50) * 4 + kind]   anchor-relative
    feat[400 + anchor]                          anchor one-hot
    Anchor = STM's rear-most piece in STM-POV
             (highest-numbered set bit of the STM piece bitboard,
              after the v2 mirror+colour-swap is applied).

Both networks share the same 200 → 64 → 32 → 1 ReLU topology so the
signal we measure is purely "does the new encoding help", not
"deeper net helps". The HalfMen lite path adds a small dropout to
stop the bigger input from overfitting outright on small datasets.

Decision rule (printed at the end):
    val MSE delta >  +3% → HalfMen worse. Stop.
    val MSE delta in (-3%, +3%) → noise. Need more data to decide.
    val MSE delta <  -3% → encouraging. Worth porting to C++.

Datasets
--------
Auto-detects the magic of `--data`:
  * JNNW (38 bytes/record, post-Cycle-1) — uses blended score+WDL loss
    `target = λ × score + (1-λ) × wdl × WDL_PSEUDO_SCALE` matching
    tools/train_v3.py. WDL_PSEUDO_SCALE = 800, λ default 0.7.
  * JNNT (37 bytes/record, legacy)        — falls back to MSE on the
    raw STM-POV score (no WDL signal in the file).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

NUM_SQUARES        = 50
NUM_KINDS          = 4
NUM_ABS_FEATS      = NUM_SQUARES * NUM_KINDS  # 200
NUM_HALFMEN_FEATS  = 200 + 200 + 50            # 450

DATASET_JNNT_MAGIC     = b"JNNT"
DATASET_JNNT_RECORD_SZ = 37
DATASET_JNNW_MAGIC     = b"JNNW"
DATASET_JNNW_RECORD_SZ = 38

WDL_PSEUDO_SCALE = 800.0  # match tools/train_v3.py


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
def load_records(path: Path):
    """Return (bbs[N,4], stm[N], score[N], wdl[N] or None)."""
    raw = path.read_bytes()
    if len(raw) < 8:
        raise ValueError(f"{path}: file too short")
    magic = raw[:4]
    if magic == DATASET_JNNW_MAGIC:
        record_sz = DATASET_JNNW_RECORD_SZ
        has_wdl   = True
    elif magic == DATASET_JNNT_MAGIC:
        record_sz = DATASET_JNNT_RECORD_SZ
        has_wdl   = False
    else:
        raise ValueError(f"{path}: unknown magic {magic!r}")

    count = struct.unpack_from("<I", raw, 4)[0]
    if 8 + count * record_sz != len(raw):
        raise ValueError(
            f"{path}: size {len(raw)} != header-implied "
            f"{8 + count * record_sz}")

    body  = np.frombuffer(raw[8:8 + count * record_sz],
                          dtype=np.uint8).reshape(count, record_sz)
    bbs   = body[:, :32].view(np.uint64).reshape(count, 4)
    stm   = body[:, 32]
    score = body[:, 33:37].view(np.int32).reshape(count).copy()
    if has_wdl:
        # WDL byte is signed int8: +1 = win, 0 = draw, -1 = loss (STM-POV).
        wdl = body[:, 37].view(np.int8).reshape(count).astype(np.float32)
    else:
        wdl = None
    return bbs, stm, score, wdl


def encode_v2(bbs, stm):
    """Same as tools/train_mlp.py: STM-POV with mirror+swap on
    black-to-move. Returns float32 (N, 200)."""
    n = len(stm)
    X = np.zeros((n, NUM_ABS_FEATS), dtype=np.float32)
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
        for kind, src in enumerate((2, 3, 0, 1)):  # swap stm/opp
            for sq in range(NUM_SQUARES):
                bit = np.uint64(1) << np.uint64(sq)
                X[idx, (NUM_SQUARES - 1 - sq) * NUM_KINDS + kind] = (
                    (sub[:, src] & bit) > 0).astype(np.float32)
    return X


def find_anchors(bbs, stm):
    """Return (N,) int32 array, anchor square index in STM-POV
    (= highest set bit of STM's piece bitboard after the v2 mirror).

    For white-to-move (no transformation): anchor = MSB of (white_men |
    white_kings).
    For black-to-move (mirror+swap): the STM pieces are originally the
    black ones; their highest STM-POV bit is `49 - (LSB of black bb)`.
    """
    n = len(stm)
    anchors = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if stm[i] == 0:
            stm_bb = int(bbs[i, 0]) | int(bbs[i, 1])
            anchors[i] = (stm_bb.bit_length() - 1) if stm_bb else 49
        else:
            stm_bb = int(bbs[i, 2]) | int(bbs[i, 3])
            if stm_bb == 0:
                anchors[i] = 49
            else:
                lsb = (stm_bb & -stm_bb).bit_length() - 1
                anchors[i] = 49 - lsb
    return anchors


def encode_halfmen(bbs, stm):
    """450 features: 200 absolute + 200 anchor-relative + 50 anchor one-hot."""
    n = len(stm)
    X = np.zeros((n, NUM_HALFMEN_FEATS), dtype=np.float32)

    # First 200: same as v2 absolute.
    X_v2 = encode_v2(bbs, stm)
    X[:, :200] = X_v2

    # Anchor per record.
    anchors = find_anchors(bbs, stm)

    # Anchor one-hot: feat[400 + anchor].
    X[np.arange(n), 400 + anchors] = 1.0

    # Anchor-relative features: derive from X_v2 + anchors.
    # X_v2 is (N, 200); active position (sq, kind) → feat 200 + rel*4 + kind
    # with rel = (sq - anchor) % 50.
    # Vectorise over kinds, loop over squares.
    for kind in range(NUM_KINDS):
        # extract the column for this kind across all squares
        # shape (N, NUM_SQUARES) where entry i,sq = X_v2[i, sq*4+kind]
        col_idx = np.arange(NUM_SQUARES) * NUM_KINDS + kind
        sub = X_v2[:, col_idx]  # (N, NUM_SQUARES)
        for sq in range(NUM_SQUARES):
            mask = sub[:, sq] > 0
            if not mask.any():
                continue
            rel = (sq - anchors[mask]) % NUM_SQUARES
            target = 200 + rel * NUM_KINDS + kind
            X[np.where(mask)[0], target] = 1.0
    return X


# ---------------------------------------------------------------------------
# Model & training
# ---------------------------------------------------------------------------
def make_mlp(input_dim: int, hidden1: int = 64, hidden2: int = 32,
             dropout: float = 0.0) -> nn.Module:
    layers = [nn.Linear(input_dim, hidden1), nn.ReLU()]
    if dropout > 0:
        layers.append(nn.Dropout(dropout))
    layers += [nn.Linear(hidden1, hidden2), nn.ReLU()]
    if dropout > 0:
        layers.append(nn.Dropout(dropout))
    layers += [nn.Linear(hidden2, 1)]
    return nn.Sequential(*layers)


def train(model: nn.Module, X: np.ndarray, y: np.ndarray, *,
          epochs: int = 30, batch: int = 512, lr: float = 1e-3,
          wd: float = 1e-5, seed: int = 42, val_frac: float = 0.1,
          clip: float = 2000.0):
    """y must be the *blended* target (score + WDL) for an apples-to-
    apples comparison with train_v3.py. The loss is plain MSE on it."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(X))
    X = X[perm].astype(np.float32, copy=False)
    y = np.clip(y[perm], -clip, clip).astype(np.float32, copy=False)

    n_val = max(1, int(len(X) * val_frac))
    X_val = torch.from_numpy(X[:n_val])
    y_val = torch.from_numpy(y[:n_val])
    X_tr  = torch.from_numpy(X[n_val:])
    y_tr  = torch.from_numpy(y[n_val:])

    loader  = DataLoader(TensorDataset(X_tr, y_tr),
                         batch_size=batch, shuffle=True)
    opt     = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    for ep in range(1, epochs + 1):
        model.train()
        running, n = 0.0, 0
        for xb, yb in loader:
            opt.zero_grad()
            loss = loss_fn(model(xb).squeeze(-1), yb)
            loss.backward()
            opt.step()
            running += loss.item() * len(xb)
            n       += len(xb)
        model.eval()
        with torch.no_grad():
            val = loss_fn(model(X_val).squeeze(-1), y_val).item()
        marker = " *" if val < best_val else ""
        if val < best_val:
            best_val = val
        print(f"  epoch {ep:3d}: train MSE={running / n:9.1f}  val MSE={val:9.1f}{marker}")
    return best_val


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--data",   type=Path, required=True)
    p.add_argument("--epochs", type=int,   default=20)
    p.add_argument("--lambda", dest="lam", type=float, default=0.7,
                   help="weight of the deep-search score in the blended "
                        "target (rest goes to WDL × 800). Only used on "
                        "JNNW datasets; ignored for JNNT.")
    args = p.parse_args(argv)

    print(f"loading {args.data} …")
    bbs, stm, score, wdl = load_records(args.data)
    n = len(stm)
    print(f"  {n} records  (magic={'JNNW' if wdl is not None else 'JNNT'})")
    if wdl is not None:
        # JNNW already stores WDL in STM-POV from the sample; same convention
        # for the score field. No sign flip needed in either case.
        wf = wdl.astype(np.float32)
        sf = score.astype(np.float32)
        y = (args.lam * sf + (1.0 - args.lam) * wf * WDL_PSEUDO_SCALE)
        print(f"  blended target: λ={args.lam}, WDL pseudo-scale={WDL_PSEUDO_SCALE}")
        print(f"  WDL distribution: "
              f"W={(wdl > 0).mean()*100:.1f}% "
              f"D={(wdl == 0).mean()*100:.1f}% "
              f"L={(wdl < 0).mean()*100:.1f}%")
    else:
        # JNNT: legacy score-only target. Need a sign flip because old
        # gen-data wrote scores from white's POV; the new gen-data-wdl
        # writes them in STM-POV directly. Keep the legacy behaviour
        # for backward compat.
        y = np.where(stm == 0, score, -score).astype(np.float32)

    print("\n=== v2 baseline (200 features, no dropout) ===")
    X_v2 = encode_v2(bbs, stm)
    print(f"  X shape: {X_v2.shape}")
    print(f"  active features per row (mean): {(X_v2 > 0).sum() / n:.1f}")
    m_v2 = make_mlp(NUM_ABS_FEATS, dropout=0.0)
    n_params = sum(p.numel() for p in m_v2.parameters())
    print(f"  params: {n_params}")
    bv = train(m_v2, X_v2, y, epochs=args.epochs)

    print("\n=== HalfMen lite (450 features, dropout 0.1) ===")
    X_h = encode_halfmen(bbs, stm)
    print(f"  X shape: {X_h.shape}")
    print(f"  active features per row (mean): {(X_h > 0).sum() / n:.1f}")
    m_h = make_mlp(NUM_HALFMEN_FEATS, dropout=0.1)
    n_params = sum(p.numel() for p in m_h.parameters())
    print(f"  params: {n_params}")
    bh = train(m_h, X_h, y, epochs=args.epochs)

    print("\n=== Verdict ===")
    print(f"  v2 baseline best val MSE:  {bv:9.1f}  (RMSE {bv**0.5:6.1f})")
    print(f"  HalfMen lite best val MSE: {bh:9.1f}  (RMSE {bh**0.5:6.1f})")
    delta_pct = (bh - bv) / bv * 100
    print(f"  delta: {delta_pct:+.1f}%")
    if delta_pct < -3:
        print("  → ENCOURAGING: HalfMen captures more signal. Worth implementing in C++.")
    elif delta_pct < 3:
        print("  → INCONCLUSIVE: within noise. Needs more data or different anchor.")
    else:
        print("  → NOT WORTH IT: HalfMen worse. Anchor / encoding probably wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
