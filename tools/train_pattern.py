#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Train a PatternNetwork (v1: 8 patterns × 4 squares each, 5000 weights)
on a JNNW self-play dataset.

The pattern set mirrors `PatternNetwork::default_v1()` in
src/pattern_network.cpp — keep them in sync if you adjust either.

Loss: MSE on score (centipawn) + optional BCE on WDL, blended by
`--lambda` (default 0.7: 70% score MSE, 30% WDL BCE — matches the
proven Cycle 8 v5 ratio). Quantises trained float32 weights to int32
on save (centipawn scale) for the JPAT format consumed by the C++
PatternNetwork loader.

Usage:
    python3 tools/train_pattern.py \\
        --data depth20-1M.bin \\
        --out  trained.jpat \\
        --epochs 30 --batch 4096 --lambda 0.7
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# v1 pattern set — keep in sync with V1_PATTERNS in pattern_network.cpp.
V1_PATTERNS: list[list[int]] = [
    [ 1,  2,  6,  7],   # NW
    [ 3,  4,  8,  9],   # N
    [16, 17, 21, 22],   # mid-W
    [18, 19, 23, 24],   # centre
    [25, 26, 30, 31],   # centre-S
    [32, 33, 37, 38],   # mid-S
    [42, 43, 47, 48],   # S
    [44, 45, 49, 50],   # SE
]

# JNNW: 4×u64 bitboards (32 B) + 1 B stm + 4 B score + 1 B wdl = 38 B/record.
JNNW_RECORD = struct.Struct("<QQQQBiB")
JNNW_RECORD_SIZE = 38
JNNW_HEADER = 8  # 4 B magic + 4 B count


def load_jnnw(path: Path, max_records: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (bitboards 4×N, stm N, score N, wdl N) as int arrays."""
    raw = path.read_bytes()
    assert raw[:4] == b"JNNW", f"{path}: bad magic"
    count = struct.unpack_from("<I", raw, 4)[0]
    if max_records > 0:
        count = min(count, max_records)

    bbs   = np.empty((4, count), dtype=np.uint64)
    stm   = np.empty(count, dtype=np.uint8)
    score = np.empty(count, dtype=np.int32)
    wdl   = np.empty(count, dtype=np.int8)

    off = JNNW_HEADER
    for i in range(count):
        wm, wk, bm, bk, s, sc, w = JNNW_RECORD.unpack_from(raw, off)
        bbs[0, i] = wm
        bbs[1, i] = wk
        bbs[2, i] = bm
        bbs[3, i] = bk
        stm[i]    = s
        score[i]  = sc
        # wdl is unpacked as unsigned u8; the on-disk byte is signed
        # int8 (-1 / 0 / +1), so reinterpret manually.
        wdl[i]    = w if w < 128 else w - 256
        off += JNNW_RECORD_SIZE

    return bbs, stm, score, wdl


def pattern_indices(bbs: np.ndarray, patterns: list[list[int]]) -> np.ndarray:
    """For each position N × each pattern P, compute the base-5 bucket
    index. Returns int64 array of shape (P, N)."""
    n_patterns = len(patterns)
    n_positions = bbs.shape[1]
    out = np.zeros((n_patterns, n_positions), dtype=np.int64)
    for pi, sqs in enumerate(patterns):
        # For each square in the pattern, derive its 0..4 state in [N].
        # State: 0 = empty, 1 = W-man, 2 = W-king, 3 = B-man, 4 = B-king.
        mult = 1
        for sq in sqs:
            bit = sq - 1
            mask = np.uint64(1) << np.uint64(bit)
            wm = (bbs[0] & mask) != 0
            wk = (bbs[1] & mask) != 0
            bm = (bbs[2] & mask) != 0
            bk = (bbs[3] & mask) != 0
            state = np.zeros(n_positions, dtype=np.int64)
            state[wm] = 1
            state[wk] = 2
            state[bm] = 3
            state[bk] = 4
            out[pi] += state * mult
            mult *= 5
    return out


class PatternModel(nn.Module):
    def __init__(self, patterns: list[list[int]]):
        super().__init__()
        self.tables = nn.ModuleList([
            nn.Embedding(5 ** len(p), 1) for p in patterns
        ])
        for t in self.tables:
            nn.init.zeros_(t.weight)
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self, indices: torch.Tensor) -> torch.Tensor:
        # indices: (P, N) int64
        # output:  (N,)   float32
        s = self.bias.expand(indices.shape[1]).clone()
        for pi, table in enumerate(self.tables):
            s = s + table(indices[pi]).squeeze(-1)
        return s


def save_jpat(model: PatternModel, patterns: list[list[int]], out_path: Path) -> None:
    """Quantise float32 weights to int32 centipawn and write JPAT."""
    with out_path.open("wb") as f:
        f.write(b"JPAT")
        f.write(struct.pack("<I", 1))                        # version
        f.write(struct.pack("<I", len(patterns)))            # num_patterns
        bias_int = int(round(model.bias.item()))
        f.write(struct.pack("<i", bias_int))                 # bias
        for pi, sqs in enumerate(patterns):
            k = len(sqs)
            f.write(struct.pack("<B", k))                    # num_squares
            f.write(bytes(sqs))                              # squares
            weights = model.tables[pi].weight.detach().cpu().numpy().flatten()
            quantised = np.round(weights).clip(-2**31, 2**31 - 1).astype(np.int32)
            f.write(quantised.tobytes())


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", required=True, type=Path,
                   help="JNNW dataset")
    p.add_argument("--out",  required=True, type=Path,
                   help="output JPAT file")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch",  type=int, default=4096)
    p.add_argument("--lr",     type=float, default=1e-2)
    p.add_argument("--lambda", dest="lam", type=float, default=0.7,
                   help="loss blend: lam * score_MSE + (1-lam) * wdl_BCE")
    p.add_argument("--max-records", type=int, default=0,
                   help="cap on loaded records (0 = full dataset)")
    p.add_argument("--val-frac",    type=float, default=0.05)
    p.add_argument("--seed",        type=int, default=42)
    args = p.parse_args(argv)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    print(f"loading {args.data}...", flush=True)
    bbs, stm, score, wdl = load_jnnw(args.data, args.max_records)
    n = bbs.shape[1]
    print(f"  {n} records loaded", flush=True)

    print(f"encoding pattern indices ({len(V1_PATTERNS)} patterns)...", flush=True)
    pidx = pattern_indices(bbs, V1_PATTERNS)
    print(f"  done, shape={pidx.shape}", flush=True)

    # Sign-flip the score for STM=Black so the network always sees
    # white-POV (matches the eval convention of MLPNetworkQ and the
    # C++ PatternNetwork: stored weights are white-POV, evaluate()
    # flips at output time).
    score_w = score.astype(np.float32)
    score_w[stm == 1] *= -1
    wdl_w = wdl.astype(np.float32)
    wdl_w[stm == 1] *= -1

    # Train/val split.
    perm = np.random.permutation(n)
    val_n = int(n * args.val_frac)
    val_idx, train_idx = perm[:val_n], perm[val_n:]

    pidx_t = torch.from_numpy(pidx)
    score_t = torch.from_numpy(score_w)
    wdl_t   = torch.from_numpy(wdl_w)

    model = PatternModel(V1_PATTERNS)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    for epoch in range(args.epochs):
        model.train()
        np.random.shuffle(train_idx)
        total_loss = 0.0
        nb = 0
        for off in range(0, len(train_idx), args.batch):
            batch_idx = train_idx[off:off + args.batch]
            idx_batch = pidx_t[:, batch_idx]
            score_batch = score_t[batch_idx]
            wdl_batch = wdl_t[batch_idx]

            pred = model(idx_batch)
            # Score MSE in centipawn space.
            score_mse = F.mse_loss(pred, score_batch)
            # WDL BCE: sigmoid(pred/400) vs (wdl+1)/2.
            wdl_prob = (wdl_batch + 1.0) * 0.5
            wdl_bce = F.binary_cross_entropy_with_logits(pred / 400.0, wdl_prob)
            loss = args.lam * score_mse + (1.0 - args.lam) * wdl_bce * 50000.0

            opt.zero_grad()
            loss.backward()
            opt.step()
            total_loss += loss.item()
            nb += 1

        # Validation.
        model.eval()
        with torch.no_grad():
            val_pred = model(pidx_t[:, val_idx])
            val_mse  = F.mse_loss(val_pred, score_t[val_idx]).item()
        print(f"epoch {epoch:2d}: train_loss={total_loss/nb:10.2f}  val_mse={val_mse:10.2f}",
              flush=True)

    save_jpat(model, V1_PATTERNS, args.out)
    sz = args.out.stat().st_size
    print(f"wrote {args.out} ({sz} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
