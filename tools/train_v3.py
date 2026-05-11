#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Cycle-2 trainer for the NNUE refonte: compare several MLP
architectures on a single JNNW dataset and report which one
generalises best.

Inputs
------
A JNNW file produced by `./build/jass --gen-data-wdl` (or the
`gen-data-wdl` workflow). Each record carries the bitboards, the
STM, a deep-search score (STM-POV centipawn) and the WDL outcome of
the game it was sampled from (+1/0/-1, STM-POV at sample time).

Loss
----
Plain MSE on a blended target — the broken sigmoid-BCE formulation
of the early WDL scout is replaced by the same formulation that
worked in scout_wdl.py v2:

    target_blended = λ × score + (1 - λ) × wdl × WDL_PSEUDO_SCALE
    loss           = MSE(net_output, target_blended)

With λ = 0.7 (default) the network learns mostly the search score
while being pulled 30% toward each game's eventual outcome.

What the script does
--------------------
For every architecture in `--archs` (default: 64-32 / 128-64 /
256-128 / 512-256), train a fresh MLP from scratch on the same
data and same hyperparameters, with the SAME train/val split. Print
a sorted summary of best validation MSE so the architecture
selection is apples-to-apples.

Optionally export each model in the JNNM binary format
(version 2, STM-relative encoding). Note that the C++ `MLPNetwork`
currently hard-codes HIDDEN1=64 / HIDDEN2=32 in its template-style
storage; loading a wider-architecture JNNM will fail the dim check
in C++ until the loader is made runtime-dimensioned in Cycle 3.

Usage
-----
    python3 tools/train_v3.py \\
        --data selfplay-wdl.bin \\
        --archs 64-32 128-64 256-128 \\
        --epochs 30 \\
        --out-dir trained_v3
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


# ---------------------------------------------------------------------------
# Dataset (JNNW reader)
# ---------------------------------------------------------------------------
NUM_SQUARES        = 50
NUM_KINDS          = 4
NUM_FEATS          = NUM_SQUARES * NUM_KINDS
DATASET_MAGIC_WDL  = b"JNNW"
DATASET_RECORD_SZ  = 38

# Match the JNNM v2 binary format used by tools/train_mlp.py.
JNNM_MAGIC   = b"JNNM"
JNNM_VERSION = 2

# Stockfish-style pseudo-score for a known win/loss outcome.
WDL_PSEUDO_SCALE = 800.0


def load_records(path: Path):
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != DATASET_MAGIC_WDL:
        raise ValueError(f"{path}: bad magic — expected JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * DATASET_RECORD_SZ
    if len(raw) != expected:
        raise ValueError(f"{path}: expected {expected} bytes, got {len(raw)}")

    body  = np.frombuffer(raw[8:], dtype=np.uint8).reshape(count, DATASET_RECORD_SZ)
    bbs   = body[:, :32].view(np.uint64).reshape(count, 4)
    stm   = body[:, 32]
    score = body[:, 33:37].view(np.int32).reshape(count)
    wdl   = body[:, 37].view(np.int8).reshape(count)

    # STM-POV one-hot encoding (mirror + colour swap on black-to-move),
    # identical to tools/train_mlp.py.
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

    y_score = np.where(stm == 0, score, -score).astype(np.float32)
    y_wdl   = np.where(stm == 0, wdl,   -wdl  ).astype(np.float32)
    return X, y_score, y_wdl


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class MLP(nn.Module):
    def __init__(self, hidden_sizes: list[int]):
        super().__init__()
        layers: list[nn.Module] = []
        prev = NUM_FEATS
        for h in hidden_sizes:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def parse_arch(s: str) -> list[int]:
    """`64-32` → [64, 32]; `256-128-64` → [256, 128, 64]."""
    return [int(x) for x in s.split("-")]


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------
def blended_mse(pred: torch.Tensor,
                target_score: torch.Tensor,
                target_wdl: torch.Tensor,
                lam: float) -> torch.Tensor:
    target = lam * target_score + (1.0 - lam) * target_wdl * WDL_PSEUDO_SCALE
    return ((pred - target) ** 2).mean()


def mse_score(pred: torch.Tensor, target_score: torch.Tensor) -> float:
    return float(((pred - target_score) ** 2).mean().item())


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(model: nn.Module, X: np.ndarray, y_score: np.ndarray, y_wdl: np.ndarray,
          *, epochs: int, batch: int, lr: float, wd: float, lam: float,
          clip: float, val_frac: float, seed: int, patience: int) -> tuple[float, dict]:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(X))
    X = X[perm]
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
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    best_val   = float("inf")
    best_state = None
    bad_eps    = 0
    history    = {"train": [], "val": []}
    for ep in range(1, epochs + 1):
        model.train()
        running, n = 0.0, 0
        for xb, sb, wb in loader:
            opt.zero_grad()
            pred = model(xb)
            loss = blended_mse(pred, sb, wb, lam)
            loss.backward()
            opt.step()
            running += loss.item() * len(xb)
            n       += len(xb)
        train_loss = running / n

        model.eval()
        with torch.no_grad():
            pv = model(X_val)
            val_mse = mse_score(pv, s_val)
        history["train"].append(train_loss)
        history["val"].append(val_mse)

        marker = ""
        if val_mse < best_val - 1e-3:
            best_val   = val_mse
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            bad_eps    = 0
            marker     = " *"
        else:
            bad_eps += 1
        print(f"  epoch {ep:3d}: train={train_loss:9.1f}  val={val_mse:9.1f}{marker}")
        if bad_eps >= patience:
            print(f"  early-stop at epoch {ep}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return best_val, history


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def save_jnnm(model: MLP, hidden_sizes: list[int], path: Path) -> None:
    """Serialize an MLP to the JNNM v2 binary format.

    Note: the production C++ MLPNetwork class still hard-codes
    HIDDEN1=64, HIDDEN2=32 and rejects other dimensions at load
    time. This export is forward-compatible — when the C++ loader is
    runtime-dimensioned in Cycle 3, the same files will become
    directly consumable.

    Only flat 2-hidden-layer architectures are supported by JNNM v2
    (the format has hidden1 / hidden2 fields). Deeper architectures
    are skipped silently here; the trainer still reports their val
    MSE for selection.
    """
    if len(hidden_sizes) != 2:
        print(f"  (skipping JNNM export for {len(hidden_sizes)}-hidden-layer arch)")
        return
    h1, h2 = hidden_sizes
    layers = [m for m in model.net if isinstance(m, nn.Linear)]
    assert len(layers) == 3
    w1 = layers[0].weight.detach().cpu().numpy().astype(np.float32)
    b1 = layers[0].bias  .detach().cpu().numpy().astype(np.float32)
    w2 = layers[1].weight.detach().cpu().numpy().astype(np.float32)
    b2 = layers[1].bias  .detach().cpu().numpy().astype(np.float32)
    w3 = layers[2].weight.detach().cpu().numpy().astype(np.float32).reshape(-1)
    b3 = float(layers[2].bias.detach().cpu().item())

    with path.open("wb") as f:
        f.write(JNNM_MAGIC)
        f.write(struct.pack("<IIIII", JNNM_VERSION, NUM_FEATS, h1, h2, 1))
        f.write(w1.tobytes())
        f.write(b1.tobytes())
        f.write(w2.tobytes())
        f.write(b2.tobytes())
        f.write(w3.tobytes())
        f.write(struct.pack("<f", b3))
    print(f"  wrote {path} ({path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--data",   type=Path, required=True)
    p.add_argument("--archs",  nargs="+", default=["64-32", "128-64", "256-128", "512-256"],
                   help="list of architectures to compare (e.g. 64-32 128-64-32)")
    p.add_argument("--epochs",   type=int,   default=30)
    p.add_argument("--batch",    type=int,   default=512)
    p.add_argument("--lr",       type=float, default=1e-3)
    p.add_argument("--wd",       type=float, default=1e-5)
    p.add_argument("--lambda",   dest="lam", type=float, default=0.7,
                   help="loss blend: 1.0 = pure score, 0.0 = pure WDL pseudo-score")
    p.add_argument("--clip",     type=float, default=2000.0,
                   help="absolute target clip (centipawns)")
    p.add_argument("--val-frac", type=float, default=0.1)
    p.add_argument("--seed",     type=int,   default=42)
    p.add_argument("--patience", type=int,   default=8)
    p.add_argument("--out-dir",  type=Path,  default=Path("trained_v3"),
                   help="directory to write JNNM exports for 2-hidden-layer archs")
    args = p.parse_args(argv)

    print(f"loading {args.data} …")
    t0 = time.time()
    X, y_score, y_wdl = load_records(args.data)
    n = len(X)
    print(f"  {n} records  ({time.time() - t0:.1f}s to encode)")
    win  = (y_wdl > 0).sum() / n
    draw = (y_wdl == 0).sum() / n
    loss = (y_wdl < 0).sum() / n
    print(f"  WDL distribution: W={win:.1%} D={draw:.1%} L={loss:.1%}")
    print(f"  score range: [{y_score.min():.0f}, {y_score.max():.0f}]  "
          f"mean={y_score.mean():+.1f}  std={y_score.std():.1f}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for arch_str in args.archs:
        hidden = parse_arch(arch_str)
        print(f"\n=== arch {arch_str} ===")
        model    = MLP(hidden)
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  params: {n_params:,}")

        t = time.time()
        best_val, history = train(
            model, X, y_score, y_wdl,
            epochs=args.epochs, batch=args.batch, lr=args.lr, wd=args.wd,
            lam=args.lam, clip=args.clip, val_frac=args.val_frac,
            seed=args.seed, patience=args.patience)
        elapsed = time.time() - t

        results[arch_str] = {
            "arch": arch_str,
            "hidden": hidden,
            "params": n_params,
            "val_mse": best_val,
            "val_rmse": best_val ** 0.5,
            "history": history,
            "elapsed_s": elapsed,
        }

        out_path = args.out_dir / f"nnue-{arch_str}.bin"
        save_jnnm(model, hidden, out_path)

    print("\n=== Summary (sorted by val MSE) ===")
    print(f"  {'arch':<14s}  {'params':>10s}  {'val MSE':>10s}  {'val RMSE':>9s}  {'time':>7s}")
    for k in sorted(results, key=lambda k: results[k]["val_mse"]):
        r = results[k]
        print(f"  {r['arch']:<14s}  {r['params']:>10,d}  "
              f"{r['val_mse']:>10.1f}  {r['val_rmse']:>9.1f}  "
              f"{r['elapsed_s']:>6.0f}s")

    # Persist the comparison so it can be diffed across data-pipeline
    # generations later.
    summary_path = args.out_dir / "summary.json"
    with summary_path.open("w") as f:
        json.dump({k: {kk: vv for kk, vv in v.items() if kk != "history"}
                   for k, v in results.items()}, f, indent=2)
    print(f"\nsummary → {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
