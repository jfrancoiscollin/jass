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
NUM_FEATS_V2       = NUM_SQUARES * NUM_KINDS       # 200
NUM_FEATS_HALFMEN  = 200 + 200 + 50                # 450 (abs + rel + anchor)
NUM_FEATS          = NUM_FEATS_V2  # kept as alias for legacy callers
DATASET_MAGIC_WDL  = b"JNNW"
DATASET_RECORD_SZ  = 38

# JNNM binary format. v3 adds runtime input_dim (200 or 450) so HalfMen
# weights can be loaded by the C++ MLPNetwork. v2 files (input_dim=200,
# implicit V2 encoding) are still accepted by the loader.
JNNM_MAGIC   = b"JNNM"
JNNM_VERSION = 3

# Stockfish-style pseudo-score for a known win/loss outcome.
WDL_PSEUDO_SCALE = 800.0

# Supported input encodings.
ENCODING_V2      = "v2"
ENCODING_HALFMEN = "halfmen"


def input_dim_for(encoding: str) -> int:
    if encoding == ENCODING_V2:      return NUM_FEATS_V2
    if encoding == ENCODING_HALFMEN: return NUM_FEATS_HALFMEN
    raise ValueError(f"unknown encoding {encoding!r}")


def _encode_v2(bbs: np.ndarray, stm: np.ndarray) -> np.ndarray:
    """STM-POV dense 200-feature encoding (mirror+colour-swap on
    black-to-move). Returns float32 (N, 200)."""
    count = len(stm)
    X = np.zeros((count, NUM_FEATS_V2), dtype=np.float32)
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


def _find_anchors_halfmen(bbs: np.ndarray, stm: np.ndarray) -> np.ndarray:
    """Anchor per record in STM-POV (0..49). Same definition as
    scout_halfmen.find_anchors and src/nnue.cpp::compute_anchor:
      * white-to-move (no mirror): anchor = MSB of (white_men | white_kings)
      * black-to-move (mirror): anchor = 49 - LSB of (black_men | black_kings)
    Falls back to 49 when STM has no pieces (should never happen
    during search but defensive)."""
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
    """HalfMen lite 450-feature encoding: 200 absolute + 200 anchor-
    relative + 50 anchor one-hot. Same layout as the scout and the
    C++ MLPNetwork HalfMen path."""
    count = len(stm)
    X = np.zeros((count, NUM_FEATS_HALFMEN), dtype=np.float32)

    # Slot the v2 absolute features into the first 200 columns.
    X_v2 = _encode_v2(bbs, stm)
    X[:, :200] = X_v2

    anchors = _find_anchors_halfmen(bbs, stm)
    # Anchor one-hot at offset 400.
    X[np.arange(count), 400 + anchors] = 1.0

    # Anchor-relative columns derived from the v2 absolute features.
    for kind in range(NUM_KINDS):
        col_idx = np.arange(NUM_SQUARES) * NUM_KINDS + kind
        sub = X_v2[:, col_idx]  # (N, 50)
        for sq in range(NUM_SQUARES):
            mask = sub[:, sq] > 0
            if not mask.any():
                continue
            rel = (sq - anchors[mask]) % NUM_SQUARES
            X[np.where(mask)[0], 200 + rel * NUM_KINDS + kind] = 1.0
    return X


def load_records(path: Path, encoding: str = ENCODING_V2,
                 max_records: int = 0, seed: int = 42):
    """Load a JNNW dataset and encode it to a (N, input_dim) feature
    matrix + score/wdl label arrays.

    `max_records` caps the number of records loaded BEFORE encoding —
    important for memory on big master corpora: HalfMen encoding
    materialises a (N, 450) float32 matrix, which is 1.7 GB per 1M
    records. On a 15 GB host like CCX23 a 4.74M-record master corpus
    OOMs the encoder before training starts (rc=137 = SIGKILL).

    When `max_records > 0` and the file has more records, a random
    subset of size `max_records` is selected (stable across runs via
    `seed`) so we get the rating-spread of the full corpus rather
    than just the chronologically-first slice.
    """
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

    # Pre-encoding subsample. Important: the slicing here is on the
    # raw bitboard / stm / score / wdl arrays, BEFORE the expensive
    # HalfMen encoding. That's what saves the memory.
    if max_records > 0 and count > max_records:
        rng = np.random.default_rng(seed)
        idx = rng.choice(count, max_records, replace=False)
        bbs   = bbs[idx]
        stm   = stm[idx]
        score = score[idx]
        wdl   = wdl[idx]
        count = max_records

    if encoding == ENCODING_V2:
        X = _encode_v2(bbs, stm)
    elif encoding == ENCODING_HALFMEN:
        X = _encode_halfmen(bbs, stm)
    else:
        raise ValueError(f"unknown encoding {encoding!r}")

    # The dataset stores both `score` and `wdl` in STM-POV at sample
    # time (see src/main.cpp:219-220). Our feature encoding (_encode_v2
    # and _encode_halfmen) is *also* STM-POV (mirror+colour-swap for
    # black-to-move) so the right thing is to keep the labels in
    # STM-POV verbatim, matching the input convention and matching what
    # the C++ MLPNetwork::evaluate path expects (STM-POV output by
    # construction; see comment at src/nnue.cpp:313).
    #
    # A previous version of this file applied `np.where(stm==0, x, -x)`
    # which silently re-projected the labels to white-POV, leaving the
    # input STM-POV and the label white-POV — the trained network then
    # produced white-POV outputs, which the C++ runtime consumed as if
    # they were STM-POV. Net effect: every black-to-move evaluation
    # was sign-flipped, and benchmarks against the handcrafted eval
    # collapsed to 0/18 (see PR following the diagnosis on 2026-05-18).
    y_score = score.astype(np.float32)
    y_wdl   = wdl.astype(np.float32)
    return X, y_score, y_wdl


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class MLP(nn.Module):
    def __init__(self, input_dim: int, hidden_sizes: list[int]):
        super().__init__()
        self.input_dim = input_dim
        layers: list[nn.Module] = []
        prev = input_dim
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
    """Original scalar-lambda blended MSE — kept for clarity and back-compat
    tests, no longer used in the training loop (replaced by the per-record
    weighted form below)."""
    target = lam * target_score + (1.0 - lam) * target_wdl * WDL_PSEUDO_SCALE
    return ((pred - target) ** 2).mean()


def blended_mse_weighted(pred: torch.Tensor,
                         target_score: torch.Tensor,
                         target_wdl: torch.Tensor,
                         lam_per: torch.Tensor,
                         weight_per: torch.Tensor) -> torch.Tensor:
    """Per-record blended MSE used when training on a mix of self-play
    and master-game records (Cycle 8). Each record carries its own
    `lam` (so master records with `score=0` can be pure WDL via
    `lam=0.0`) and its own scalar weight (so master records can be
    up- or down-weighted relative to self-play). Reduces to the
    scalar-lambda form when both arrays are uniform."""
    target = lam_per * target_score \
           + (1.0 - lam_per) * target_wdl * WDL_PSEUDO_SCALE
    per_record_sq_err = weight_per * (pred - target) ** 2
    return per_record_sq_err.mean()


def mse_score(pred: torch.Tensor, target_score: torch.Tensor) -> float:
    return float(((pred - target_score) ** 2).mean().item())


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------
def train(model: nn.Module, X: np.ndarray, y_score: np.ndarray, y_wdl: np.ndarray,
          *, epochs: int, batch: int, lr: float, wd: float, lam: float,
          clip: float, val_frac: float, seed: int, patience: int,
          lam_per: np.ndarray | None = None,
          weight_per: np.ndarray | None = None,
          n_selfplay: int | None = None) -> tuple[float, dict]:
    """Train a model on a (possibly blended) JNNW dataset.

    The optional `lam_per` and `weight_per` arrays carry per-record
    lambda and weight values, used when blending self-play and master
    records (Cycle 8). When both are `None`, the function falls back
    to the scalar-lambda behaviour with uniform weights.

    `n_selfplay`, when given, is the count of self-play records in the
    first `n_selfplay` rows of X (master records, if any, follow).
    The validation split is taken EXCLUSIVELY from those first
    `n_selfplay` rows so the reported val MSE remains comparable
    across runs regardless of master-data presence.
    """
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)

    # Build the per-record lam / weight arrays if the caller didn't pass
    # them. From this point onward the training loop assumes both exist.
    if lam_per is None:
        lam_per = np.full(len(X), lam, dtype=np.float32)
    if weight_per is None:
        weight_per = np.ones(len(X), dtype=np.float32)
    if n_selfplay is None:
        n_selfplay = len(X)

    # Validation set is sampled BEFORE shuffling and ONLY from self-play
    # rows (the first n_selfplay rows). Master records never enter the
    # validation set so val MSE stays comparable.
    n_val = max(1, int(n_selfplay * val_frac))
    val_perm = rng.permutation(n_selfplay)
    val_idx  = val_perm[:n_val]
    tr_idx_self = val_perm[n_val:]
    # Append master rows (if any) to the train set unshuffled-here;
    # they'll be shuffled by the DataLoader together with self-play.
    tr_idx_master = np.arange(n_selfplay, len(X))
    tr_idx = np.concatenate([tr_idx_self, tr_idx_master])

    y_score_clipped = np.clip(y_score, -clip, clip).astype(np.float32, copy=False)
    y_wdl_f         = y_wdl.astype(np.float32, copy=False)

    X_val = torch.from_numpy(X[val_idx])
    s_val = torch.from_numpy(y_score_clipped[val_idx])
    X_tr  = torch.from_numpy(X[tr_idx])
    s_tr  = torch.from_numpy(y_score_clipped[tr_idx])
    w_tr  = torch.from_numpy(y_wdl_f[tr_idx])
    lam_tr    = torch.from_numpy(lam_per[tr_idx])
    weight_tr = torch.from_numpy(weight_per[tr_idx])

    loader = DataLoader(TensorDataset(X_tr, s_tr, w_tr, lam_tr, weight_tr),
                        batch_size=batch, shuffle=True)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    best_val   = float("inf")
    best_state = None
    bad_eps    = 0
    history    = {"train": [], "val": []}
    for ep in range(1, epochs + 1):
        model.train()
        running, n = 0.0, 0
        for xb, sb, wb, lam_b, w_rec_b in loader:
            opt.zero_grad()
            pred = model(xb)
            loss = blended_mse_weighted(pred, sb, wb, lam_b, w_rec_b)
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
    """Serialize an MLP to the JNNM v3 binary format. Carries the
    actual input_dim (200 for V2 dense, 450 for HalfMen) and hidden
    dims, so the runtime-dimensioned C++ MLPNetwork can load any
    2-hidden-layer arch produced by this trainer.

    Only flat 2-hidden-layer architectures are supported by JNNM
    (the format has hidden1 / hidden2 fields). Deeper architectures
    are skipped silently here; the trainer still reports their val
    MSE for selection."""
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
        f.write(struct.pack("<IIIII",
                            JNNM_VERSION, model.input_dim, h1, h2, 1))
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
    p.add_argument("--encoding", choices=[ENCODING_V2, ENCODING_HALFMEN],
                   default=ENCODING_V2,
                   help="input feature encoding (default: v2 dense 200; "
                        "halfmen adds 200 anchor-relative + 50 anchor one-hot "
                        "for a 450-feature input, beats v2 by ~25%% val MSE "
                        "at equal parameter count on 1M JNNW)")
    p.add_argument("--master-data", type=Path, default=None,
                   help="Optional second JNNW file blended into training "
                        "(Cycle 8: master games from Lidraughts via "
                        "tools/pdn_to_jnnw.py). Records here are typically "
                        "score=0 with WDL-only labels — see --master-lam.")
    p.add_argument("--master-weight", type=float, default=1.0,
                   help="Per-record weight for master records (default 1.0 "
                        "= same as self-play). >1 up-weights master records "
                        "in the loss, useful when the master corpus is small "
                        "relative to self-play.")
    p.add_argument("--master-lam", type=float, default=0.0,
                   help="Lambda for master records (0.0 = pure WDL target, "
                        "recommended since pdn_to_jnnw.py emits score=0). "
                        "Setting this higher would weight a usually-zero "
                        "score field into the master loss, which is rarely "
                        "what you want.")
    p.add_argument("--max-master-records", type=int, default=0,
                   help="Cap on the number of master records loaded. 0 = no "
                        "cap. Cap kicks in BEFORE the HalfMen encoding "
                        "materialises a (N, 450) float32 matrix, so this is "
                        "the right knob to keep memory bounded on big master "
                        "corpora (~1.7 GB per 1M records under HalfMen). On a "
                        "15 GB host (CCX23) ~2-2.5M total records is the safe "
                        "upper bound; default 0 only works when the master "
                        "file is naturally small.")
    args = p.parse_args(argv)

    input_dim = input_dim_for(args.encoding)
    print(f"loading {args.data} (encoding={args.encoding}, input_dim={input_dim}) …")
    t0 = time.time()
    X, y_score, y_wdl = load_records(args.data, encoding=args.encoding)
    n_self = len(X)
    print(f"  {n_self} self-play records  ({time.time() - t0:.1f}s to encode)")
    win  = (y_wdl > 0).sum() / n_self
    draw = (y_wdl == 0).sum() / n_self
    loss = (y_wdl < 0).sum() / n_self
    print(f"  WDL distribution: W={win:.1%} D={draw:.1%} L={loss:.1%}")
    print(f"  score range: [{y_score.min():.0f}, {y_score.max():.0f}]  "
          f"mean={y_score.mean():+.1f}  std={y_score.std():.1f}")

    # Cycle 8: optional blend with master-game records.
    lam_per    = np.full(n_self, args.lam,            dtype=np.float32)
    weight_per = np.ones (n_self,                      dtype=np.float32)
    n_master   = 0

    if args.master_data is not None:
        print(f"loading master {args.master_data} (encoding={args.encoding}) …")
        t0 = time.time()
        Xm, ym_score, ym_wdl = load_records(
            args.master_data,
            encoding=args.encoding,
            max_records=args.max_master_records,
            seed=args.seed)
        n_master = len(Xm)
        if Xm.shape[1] != X.shape[1]:
            raise SystemExit(
                f"input_dim mismatch: data={X.shape[1]} "
                f"master_data={Xm.shape[1]} — both must use the same encoding")
        print(f"  {n_master} master records  ({time.time() - t0:.1f}s to encode)")
        mwin  = (ym_wdl > 0).sum() / max(n_master, 1)
        mdraw = (ym_wdl == 0).sum() / max(n_master, 1)
        mloss = (ym_wdl < 0).sum() / max(n_master, 1)
        print(f"  master WDL: W={mwin:.1%} D={mdraw:.1%} L={mloss:.1%}")
        print(f"  master blend: weight={args.master_weight}  "
              f"lam={args.master_lam}  (pure-WDL when lam=0)")

        lam_master    = np.full(n_master, args.master_lam,    dtype=np.float32)
        weight_master = np.full(n_master, args.master_weight, dtype=np.float32)

        # IMPORTANT: self-play rows first, master rows after. The
        # `n_selfplay` parameter passed to train() relies on this.
        X        = np.concatenate([X,        Xm])
        y_score  = np.concatenate([y_score,  ym_score])
        y_wdl    = np.concatenate([y_wdl,    ym_wdl])
        lam_per  = np.concatenate([lam_per,  lam_master])
        weight_per = np.concatenate([weight_per, weight_master])
        print(f"  blended total: {len(X)} records "
              f"({n_self} self-play + {n_master} master)")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for arch_str in args.archs:
        hidden = parse_arch(arch_str)
        print(f"\n=== arch {arch_str} ===")
        model    = MLP(input_dim, hidden)
        n_params = sum(p.numel() for p in model.parameters())
        print(f"  params: {n_params:,}")

        t = time.time()
        best_val, history = train(
            model, X, y_score, y_wdl,
            epochs=args.epochs, batch=args.batch, lr=args.lr, wd=args.wd,
            lam=args.lam, clip=args.clip, val_frac=args.val_frac,
            seed=args.seed, patience=args.patience,
            lam_per=lam_per, weight_per=weight_per, n_selfplay=n_self)
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
