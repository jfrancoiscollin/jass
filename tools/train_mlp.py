#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Train a Jass `MLPNetwork` (topology 200 → 64 → 32 → 1, ReLU
activations on the two hidden layers) from a self-play dataset.

A widening to 128/64 was tried in PR #8 and lost at depth 5 by score
rate 0.444 vs the linear baseline on 90 games — over-parameterised
for 100k records of noisy depth-8 targets. We reverted to 64/32.

Pipeline
--------
    ./build/jass --gen-data 100000 selfplay.bin
    python3 tools/train_mlp.py --data selfplay.bin --out nnue.bin

The output `nnue.bin` follows the JNNM binary format consumed by
`MLPNetwork::load()` in src/nnue.cpp:

    [0..4)   magic = "JNNM"
    [4..8)   uint32 version (currently 2)
    [8..12)  uint32 input_dim   (must equal 200)
    [12..16) uint32 hidden1     (must equal 64)
    [16..20) uint32 hidden2     (must equal 32)
    [20..24) uint32 output_dim  (must equal 1)
    [24..)   little-endian float32 weights:
              w1 [HIDDEN1 × INPUT_DIM]   (row-major, neuron-major)
              b1 [HIDDEN1]
              w2 [HIDDEN2 × HIDDEN1]
              b2 [HIDDEN2]
              w3 [HIDDEN2]
              b3 [1]

Convention
----------
The network sees the board from the side-to-move's perspective:

    feat[b * 4 + 0] = STM has man  on bit b   (b in 0..49)
    feat[b * 4 + 1] = STM has king on bit b
    feat[b * 4 + 2] = OPP has man  on bit b
    feat[b * 4 + 3] = OPP has king on bit b

For black-to-move records we mirror the bit (b -> 49 - b, the bit
equivalent of FMJD square s -> 51 - s) and swap the colour role
before populating the features. The network output is therefore
already in STM-POV and the dataset's `score` field can be used as the
target verbatim — no tempo bookkeeping, no sign flip.

This bakes the rotation-by-180° + colour-swap symmetry of draughts
into the model: the same "position from my POV" maps to the same
network input regardless of which physical colour is to move,
effectively doubling the dataset.

Targets are clipped to ±2000 cp so a single decisive game cannot
dominate the loss; this matches what `tools/train.py` does for the
linear model.
"""
from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:
    sys.stderr.write(
        "error: PyTorch is required for the MLP trainer.\n"
        "       install it with:\n"
        "         pip install torch --index-url "
        "https://download.pytorch.org/whl/cpu\n"
    )
    raise

# ---------------------------------------------------------------------------
# Constants — must stay in lockstep with src/nnue.hpp (MLPNetwork).
# ---------------------------------------------------------------------------
NUM_SQUARES = 50
NUM_KINDS   = 4
NUM_FEATS   = NUM_SQUARES * NUM_KINDS  # 200
HIDDEN1     = 64
HIDDEN2     = 32

DATASET_MAGIC      = b"JNNT"
DATASET_RECORD_SZ  = 37

MLP_MAGIC   = b"JNNM"
# Bumped to 2 when the input encoding switched to STM-relative with
# board mirroring + colour swap. Must stay in lockstep with the
# constant of the same name in src/nnue.cpp.
MLP_VERSION = 2


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised loader.

    Returns
    -------
    X : (N, 200) float32 — one-hot indicators for (square × piece-kind)
                           in *STM-POV* encoding (mirror + colour swap
                           applied to black-to-move rows).
    y : (N,)    float32 — target score in STM-POV (centipawns,
                           dataset's `score` field used verbatim).
    """
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != DATASET_MAGIC:
        raise ValueError(f"{path}: bad magic — is this a Jass NNUE dataset?")
    count = struct.unpack_from("<I", raw, 4)[0]
    expected = 8 + count * DATASET_RECORD_SZ
    if len(raw) != expected:
        raise ValueError(
            f"{path}: expected {expected} bytes "
            f"(8 header + {count}×{DATASET_RECORD_SZ}), got {len(raw)}"
        )

    body  = np.frombuffer(raw[8:], dtype=np.uint8).reshape(count, DATASET_RECORD_SZ)
    bbs   = body[:, :32].view(np.uint64).reshape(count, 4)
    stm   = body[:, 32]
    score = body[:, 33:37].view(np.int32).reshape(count)

    # Bitboard slot ordering in `bbs`: 0=white-man, 1=white-king,
    # 2=black-man, 3=black-king. For STM-relative encoding we swap the
    # colour role for black-to-move rows so kind 0/1 always means the
    # STM's pieces.
    is_w = (stm == 0)
    is_b = ~is_w

    X = np.zeros((count, NUM_FEATS), dtype=np.float32)

    # White-to-move rows: identity mapping (no mirror, no swap).
    if is_w.any():
        idx_w  = np.where(is_w)[0]
        sub_w  = bbs[is_w]
        for kind, src in enumerate((0, 1, 2, 3)):
            for sq in range(NUM_SQUARES):
                bit = np.uint64(1) << np.uint64(sq)
                col = sq * NUM_KINDS + kind
                X[idx_w, col] = ((sub_w[:, src] & bit) > 0).astype(np.float32)

    # Black-to-move rows: mirror bit (49 - bit) and swap the colour
    # role so kind 0/1 = STM = black, kind 2/3 = OPP = white.
    if is_b.any():
        idx_b = np.where(is_b)[0]
        sub_b = bbs[is_b]
        for kind, src in enumerate((2, 3, 0, 1)):  # stm=black, opp=white
            for sq in range(NUM_SQUARES):
                bit = np.uint64(1) << np.uint64(sq)
                col = (NUM_SQUARES - 1 - sq) * NUM_KINDS + kind
                X[idx_b, col] = ((sub_b[:, src] & bit) > 0).astype(np.float32)

    # Targets are already in STM-POV in the dataset, so use them
    # verbatim — no sign flip, no tempo bookkeeping.
    y = score.astype(np.float32)
    return X, y


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class MLP(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(NUM_FEATS, HIDDEN1)
        self.fc2 = nn.Linear(HIDDEN1,   HIDDEN2)
        self.fc3 = nn.Linear(HIDDEN2,   1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        return self.fc3(x).squeeze(-1)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(X: np.ndarray, y: np.ndarray, *,
          epochs: int, batch_size: int, lr: float, weight_decay: float,
          val_frac: float, patience: int, clip: float, seed: int) -> MLP:
    torch.manual_seed(seed)
    rng  = np.random.default_rng(seed)
    perm = rng.permutation(len(X))
    X, y = X[perm], y[perm]
    y    = np.clip(y, -clip, clip).astype(np.float32)

    n_val = max(1, int(len(X) * val_frac))
    X_val = torch.from_numpy(X[:n_val])
    y_val = torch.from_numpy(y[:n_val])
    X_tr  = torch.from_numpy(X[n_val:])
    y_tr  = torch.from_numpy(y[n_val:])
    print(f"  train={len(X_tr)} val={len(X_val)}")

    loader   = DataLoader(TensorDataset(X_tr, y_tr),
                          batch_size=batch_size, shuffle=True, drop_last=False)
    model    = MLP()
    opt      = torch.optim.Adam(model.parameters(), lr=lr,
                                weight_decay=weight_decay)
    loss_fn  = nn.MSELoss()

    best_val   = float("inf")
    best_state = None
    bad_epochs = 0
    for ep in range(1, epochs + 1):
        model.train()
        running, n = 0.0, 0
        for xb, yb in loader:
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            running += loss.item() * len(xb)
            n       += len(xb)
        train_mse = running / n

        model.eval()
        with torch.no_grad():
            val_mse = loss_fn(model(X_val), y_val).item()

        marker = ""
        if val_mse < best_val - 1e-3:
            best_val   = val_mse
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
            bad_epochs = 0
            marker     = " *"
        else:
            bad_epochs += 1
        print(f"  epoch {ep:3d}: train MSE={train_mse:9.1f}  "
              f"val MSE={val_mse:9.1f}  "
              f"val RMSE={val_mse**0.5:6.1f}{marker}")

        if bad_epochs >= patience:
            print(f"  early-stop after {ep} epochs "
                  f"(no improvement for {patience})")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def save_mlp(model: MLP, path: Path) -> None:
    """Serialise the model in the JNNM format consumed by MLPNetwork::load()."""
    w1 = model.fc1.weight.detach().cpu().numpy().astype(np.float32)  # (64, 200)
    b1 = model.fc1.bias  .detach().cpu().numpy().astype(np.float32)
    w2 = model.fc2.weight.detach().cpu().numpy().astype(np.float32)  # (32, 64)
    b2 = model.fc2.bias  .detach().cpu().numpy().astype(np.float32)
    w3 = model.fc3.weight.detach().cpu().numpy().astype(np.float32).reshape(-1)
    b3 = float(model.fc3.bias.detach().cpu().item())

    if w1.shape != (HIDDEN1, NUM_FEATS):
        raise ValueError(f"unexpected fc1 shape {w1.shape}")
    if w2.shape != (HIDDEN2, HIDDEN1):
        raise ValueError(f"unexpected fc2 shape {w2.shape}")

    with path.open("wb") as f:
        f.write(MLP_MAGIC)
        f.write(struct.pack("<IIIII",
                            MLP_VERSION, NUM_FEATS, HIDDEN1, HIDDEN2, 1))
        f.write(w1.tobytes())
        f.write(b1.tobytes())
        f.write(w2.tobytes())
        f.write(b2.tobytes())
        f.write(w3.tobytes())
        f.write(struct.pack("<f", b3))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Train a Jass MLPNetwork from a self-play dataset.")
    p.add_argument("--data",         type=Path,  required=True,
                   help="dataset produced by `jass --gen-data`")
    p.add_argument("--out",          type=Path,  default=Path("nnue.bin"),
                   help="output weights file (default: nnue.bin)")
    p.add_argument("--epochs",       type=int,   default=30)
    p.add_argument("--batch-size",   type=int,   default=512)
    p.add_argument("--lr",           type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-5)
    p.add_argument("--val-frac",     type=float, default=0.1)
    p.add_argument("--patience",     type=int,   default=5,
                   help="early-stopping patience (epochs without "
                        "validation improvement)")
    p.add_argument("--clip",         type=float, default=2000.0,
                   help="absolute target clip in centipawns")
    p.add_argument("--seed",         type=int,   default=42)
    args = p.parse_args(argv)

    print(f"loading {args.data} …")
    t0 = time.time()
    X, y = load_dataset(args.data)
    print(f"  {X.shape[0]} records, {X.shape[1]} features  "
          f"({time.time() - t0:.1f}s)")

    print("training MLP (200 → 64 → 32 → 1, ReLU) …")
    model = train(X, y,
                  epochs=args.epochs, batch_size=args.batch_size,
                  lr=args.lr, weight_decay=args.weight_decay,
                  val_frac=args.val_frac, patience=args.patience,
                  clip=args.clip, seed=args.seed)

    save_mlp(model, args.out)
    print(f"wrote weights to {args.out} ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
