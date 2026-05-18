#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Exploratory scout: does mixing the game-outcome (WDL) signal into
the training loss beat the current pure-score MSE pipeline?

Requires a JNNW dataset (produced by `./build/jass --gen-data-wdl N path`)
that records, per sampled position:
  - the bitboards + stm + the depth-8 search score (as JNNT),
  - PLUS the WDL outcome of the game the sample came from, propagated
    back to that sample's STM perspective (+1 = STM eventually won,
    0 = draw, -1 = STM lost).

Both trainings share the same network topology (200 → 64 → 32 → 1,
ReLU) and the same MSE-on-blended-target loss formulation, so the
only moving piece is `lambda`. We treat the WDL outcome as a
saturated pseudo-score (`wdl × WDL_SCALE` cp) and blend it with the
real depth-eval score:

    target_blended = λ × score_target + (1 - λ) × (wdl × WDL_SCALE)
    loss           = MSE(network_output, target_blended)

The Stockfish-style sigmoid+BCE formulation was tried first but its
gradient saturates near zero (where most early/mid-game positions
sit), leaving the network stuck at "predict 0" with our 30k-sample
budget. Plain MSE has steep gradients everywhere; comparable to the
production train_mlp.py and scout_halfmen.py baselines.

Configurations:
  - Baseline:   λ = 1.0 (pure-score MSE, ignores WDL)
  - Mixed:      λ = 0.7 (30% pull toward the game-outcome's pseudo-score)

Verdict is printed on the val set's MSE-on-score (the metric that
actually drives play strength at inference time, since the engine
still consumes a centipawn score):

    delta < -3%  →  WDL helps, port to production
    -3% .. +3%  →  inconclusive (noise / need more data)
    > +3%       →  WDL hurts, drop

Decision matters because WDL labels need a heavier gen-data pipeline
(games must be played to terminal) — only worth it if the signal is
real.
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
NUM_FEATS          = NUM_SQUARES * NUM_KINDS  # 200
DATASET_MAGIC_WDL  = b"JNNW"
DATASET_RECORD_SZ  = 38                       # 32 + 1 + 4 + 1


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
def load_records(path: Path):
    """Returns (X, score, wdl) — X is the STM-POV feature matrix, score
    in cp (STM-POV), wdl in {-1, 0, +1}."""
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != DATASET_MAGIC_WDL:
        raise ValueError(f"{path}: bad magic — expected JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * DATASET_RECORD_SZ
    if len(raw) != expected:
        raise ValueError(
            f"{path}: expected {expected} bytes "
            f"(8 header + {count}×{DATASET_RECORD_SZ}), got {len(raw)}")

    body  = np.frombuffer(raw[8:], dtype=np.uint8).reshape(count, DATASET_RECORD_SZ)
    bbs   = body[:, :32].view(np.uint64).reshape(count, 4)
    stm   = body[:, 32]
    score = body[:, 33:37].view(np.int32).reshape(count)
    wdl   = body[:, 37].view(np.int8).reshape(count)

    # STM-POV encoding (same as tools/train_mlp.py and scout_halfmen.py).
    X = np.zeros((count, NUM_FEATS), dtype=np.float32)
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

    # Targets in STM-POV. Score is already STM-POV (engine returns it
    # via search()). For WDL we propagated it that way in --gen-data-wdl
    # too (src/main.cpp:220), so use both directly — DO NOT re-project
    # to white-POV via np.where(stm==0, x, -x): the encoding above is
    # STM-POV (mirror+colour-swap) and the C++ runtime consumes the
    # network output as STM-POV (src/nnue.cpp:313). Mixing STM-POV
    # input + white-POV label + STM-POV runtime interpretation sign-
    # flips every black-to-move evaluation. Diagnosed 2026-05-18.
    y_score = score.astype(np.float32)
    y_wdl   = wdl.astype(np.float32)
    return X, y_score, y_wdl


# ---------------------------------------------------------------------------
# Model & loss
# ---------------------------------------------------------------------------
def make_mlp(input_dim: int = 200, hidden1: int = 64, hidden2: int = 32) -> nn.Module:
    return nn.Sequential(
        nn.Linear(input_dim, hidden1),
        nn.ReLU(),
        nn.Linear(hidden1,   hidden2),
        nn.ReLU(),
        nn.Linear(hidden2,   1),
    )


WDL_PSEUDO_SCALE = 800.0  # cp value assigned to a known win (+1) / loss (-1)


def blended_mse_loss(pred_score: torch.Tensor,
                     target_score: torch.Tensor,
                     target_wdl: torch.Tensor,
                     lam: float) -> torch.Tensor:
    """λ = 1 → pure-score MSE; λ < 1 mixes in a pull toward the game
    outcome's pseudo-score (±WDL_PSEUDO_SCALE cp). Plain MSE keeps a
    steep gradient everywhere, which the sigmoid+BCE formulation
    famously doesn't on small datasets near score = 0."""
    target_blended = lam * target_score + (1.0 - lam) * (target_wdl * WDL_PSEUDO_SCALE)
    return ((pred_score - target_blended) ** 2).mean()


def mse_on_score(pred_score: torch.Tensor,
                 target_score: torch.Tensor) -> float:
    """Reporting metric — the engine consumes cp scores at inference
    time, so MSE on score is what we care about for play strength."""
    return float(((pred_score - target_score) ** 2).mean().item())


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train(model: nn.Module, X: np.ndarray, y_score: np.ndarray, y_wdl: np.ndarray,
          *, lam: float, epochs: int, batch: int = 512, lr: float = 1e-3,
          wd: float = 1e-5, seed: int = 42, val_frac: float = 0.1,
          clip: float = 2000.0) -> float:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(X))
    X       = X[perm].astype(np.float32, copy=False)
    y_score = np.clip(y_score[perm], -clip, clip).astype(np.float32, copy=False)
    y_wdl   = y_wdl[perm].astype(np.float32, copy=False)

    n_val = max(1, int(len(X) * val_frac))
    X_val = torch.from_numpy(X[:n_val])
    s_val = torch.from_numpy(y_score[:n_val])
    w_val = torch.from_numpy(y_wdl[:n_val])
    X_tr  = torch.from_numpy(X[n_val:])
    s_tr  = torch.from_numpy(y_score[n_val:])
    w_tr  = torch.from_numpy(y_wdl[n_val:])

    loader = DataLoader(TensorDataset(X_tr, s_tr, w_tr),
                        batch_size=batch, shuffle=True)
    opt    = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    best_val_mse = float("inf")
    for ep in range(1, epochs + 1):
        model.train()
        running_loss, running_n = 0.0, 0
        for xb, sb, wb in loader:
            opt.zero_grad()
            pred = model(xb).squeeze(-1)
            loss = blended_mse_loss(pred, sb, wb, lam)
            loss.backward()
            opt.step()
            running_loss += loss.item() * len(xb)
            running_n    += len(xb)
        model.eval()
        with torch.no_grad():
            pv = model(X_val).squeeze(-1)
            val_mse = mse_on_score(pv, s_val)
        marker = " *" if val_mse < best_val_mse else ""
        if val_mse < best_val_mse:
            best_val_mse = val_mse
        print(f"  epoch {ep:3d}: train MSE={running_loss / running_n:8.1f}  "
              f"val MSE={val_mse:9.1f}{marker}")
    return best_val_mse


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--data",   type=Path, required=True)
    p.add_argument("--epochs", type=int,  default=25)
    p.add_argument("--lambda-mixed", dest="lam_mixed", type=float, default=0.7)
    args = p.parse_args(argv)

    print(f"loading {args.data} …")
    X, y_score, y_wdl = load_records(args.data)
    n = len(X)
    print(f"  {n} records")
    win_rate  = (y_wdl > 0).sum() / n
    draw_rate = (y_wdl == 0).sum() / n
    loss_rate = (y_wdl < 0).sum() / n
    print(f"  WDL distribution: W={win_rate:.1%}  D={draw_rate:.1%}  L={loss_rate:.1%}")

    print("\n=== Baseline λ = 1.0 (pure score, blended-BCE) ===")
    m1 = make_mlp()
    print(f"  params: {sum(p.numel() for p in m1.parameters())}")
    val1 = train(m1, X, y_score, y_wdl, lam=1.0, epochs=args.epochs)

    print(f"\n=== Mixed λ = {args.lam_mixed} (score + WDL outcome) ===")
    m2 = make_mlp()
    val2 = train(m2, X, y_score, y_wdl, lam=args.lam_mixed, epochs=args.epochs)

    print("\n=== Verdict ===")
    print(f"  Baseline    val MSE: {val1:9.1f}  (RMSE {val1**0.5:6.1f})")
    print(f"  Mixed (λ={args.lam_mixed})  val MSE: {val2:9.1f}  (RMSE {val2**0.5:6.1f})")
    delta_pct = (val2 - val1) / val1 * 100
    print(f"  delta: {delta_pct:+.1f}%")
    if delta_pct < -3:
        print("  → ENCOURAGING: WDL signal helps. Port to production train_mlp.py.")
    elif delta_pct < 3:
        print("  → INCONCLUSIVE: within noise. Needs more data or different λ.")
    else:
        print("  → NOT WORTH IT: WDL hurts. Stick with pure-score MSE.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
