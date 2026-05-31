#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Pattern embeddings → MLP end-to-end (PARADIGM_SHIFT_OPTIONS.md option A).

Each pattern has an embedding table : nn.Embedding(base^K, embed_dim).
Per position, lookup gives N embeddings of size embed_dim each ; concat
them (N × embed_dim) and feed to a small MLP (single hidden layer ReLU).
Output = scalar score, added to skeleton features (material/king count).

Genuinely different from JPAT v1-v7 :
* v1-v6 : pattern lookup → scalar weight → linear sum
* v7    : same + scalar MLP head as residual
* This  : pattern lookup → embed_dim vector → concat → MLP (replaces
          linear sum entirely)

Each bucket carries multi-dim feature info, not just a scalar.

Usage:
    python3 tools/train_pattern_embed.py \\
        --data /path/to.jnnw --out /tmp/embed-model.pt \\
        --patterns v3 --embed-dim 4 --mlp-hidden 64 \\
        --epochs 30 --lambda 0.0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).parent))
from train_pattern import (PATTERN_SETS, load_jnnw, pattern_indices,  # noqa: E402
                           material_diffs)


class PatternEmbedMLP(nn.Module):
    """Pattern-indexed embeddings → concat → MLP → scalar score.

    Skeleton features (material, king count) are added as a small
    scalar residual. PST/balance/mobility/phase split intentionally
    omitted here for a clean A/B vs linear lookup.
    """
    def __init__(self, patterns: list[list[int]], base: int = 3,
                 embed_dim: int = 4, mlp_hidden: int = 64,
                 init_man: float = 100.0, init_king: float = 300.0):
        super().__init__()
        self.base       = base
        self.embed_dim  = embed_dim
        self.mlp_hidden = mlp_hidden
        self.num_p      = len(patterns)
        # Per-pattern embedding tables.
        self.embeddings = nn.ModuleList([
            nn.Embedding(base ** len(p), embed_dim) for p in patterns
        ])
        for e in self.embeddings:
            nn.init.normal_(e.weight, std=0.05)
        # MLP head : (N × embed_dim) → hidden → 1.
        in_dim = self.num_p * embed_dim
        self.mlp = nn.Sequential(
            nn.Linear(in_dim, mlp_hidden), nn.ReLU(),
            nn.Linear(mlp_hidden, 1),
        )
        # Skeleton scalars (init like handcrafted eval).
        self.bias       = nn.Parameter(torch.zeros(1))
        self.man_value  = nn.Parameter(torch.tensor(init_man))
        self.king_value = nn.Parameter(torch.tensor(init_king))

    def forward(self, indices: torch.Tensor,
                mat_diff: torch.Tensor, king_diff: torch.Tensor) -> torch.Tensor:
        # indices: (P, N) int64 ; mat_diff/king_diff: (N,) float32
        n = indices.shape[1]
        embeds = [e(indices[pi]) for pi, e in enumerate(self.embeddings)]
        concat = torch.cat(embeds, dim=-1)          # (N, P*embed_dim)
        mlp_out = self.mlp(concat).squeeze(-1)      # (N,)
        return (self.bias + mlp_out
                + self.man_value  * mat_diff
                + self.king_value * king_diff)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--out",  required=True, type=Path,
                   help="output PyTorch state_dict (.pt)")
    p.add_argument("--patterns", choices=list(PATTERN_SETS.keys()), default="v3")
    p.add_argument("--embed-dim",  type=int, default=4)
    p.add_argument("--mlp-hidden", type=int, default=64)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch",  type=int, default=4096)
    p.add_argument("--lr",     type=float, default=1e-3)
    p.add_argument("--lambda", dest="lam", type=float, default=0.7,
                   help="loss blend: lam * score_MSE + (1-lam) * wdl_BCE * 50000")
    p.add_argument("--score-scale", type=float, default=0.01)
    p.add_argument("--weight-decay", type=float, default=1e-5)
    p.add_argument("--max-records", type=int, default=0)
    p.add_argument("--val-frac",    type=float, default=0.05)
    p.add_argument("--seed",        type=int, default=42)
    p.add_argument("--no-stm-flip", action="store_true",
                   help="Don't flip mat_diff/king_diff for STM=Black. "
                        "Cleaner white-POV convention (the legacy flip "
                        "made the model fit a mixed reference frame).")
    args = p.parse_args(argv)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    patterns = PATTERN_SETS[args.patterns]
    print(f"loading {args.data}...", flush=True)
    bbs, stm, score, wdl = load_jnnw(args.data, args.max_records)
    n = bbs.shape[1]
    print(f"  {n} records", flush=True)

    print(f"encoding pattern indices ({len(patterns)} × base={args.base if hasattr(args,'base') else 3})...",
          flush=True)
    pidx = pattern_indices(bbs, patterns, base=3)
    mat_diff, king_diff = material_diffs(bbs)
    # White-POV sign-flip for the target. Skeleton inputs (mat_diff,
    # king_diff) stay white-POV when --no-stm-flip is set ; otherwise
    # they get flipped (legacy 0067 behavior — a mixed-frame quirk).
    score_w = score.astype(np.float32);  score_w[stm == 1] *= -1
    wdl_w   = wdl.astype(np.float32);    wdl_w[stm == 1]   *= -1
    if not args.no_stm_flip:
        mat_diff[stm == 1] *= -1
        king_diff[stm == 1] *= -1

    perm = np.random.permutation(n)
    val_n = int(n * args.val_frac)
    val_idx, train_idx = perm[:val_n], perm[val_n:]

    pidx_t      = torch.from_numpy(pidx)
    score_t     = torch.from_numpy(score_w)
    wdl_t       = torch.from_numpy(wdl_w)
    mat_diff_t  = torch.from_numpy(mat_diff)
    king_diff_t = torch.from_numpy(king_diff)

    model = PatternEmbedMLP(patterns, base=3,
                            embed_dim=args.embed_dim,
                            mlp_hidden=args.mlp_hidden)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  model: {n_params:,} params (embed_dim={args.embed_dim} "
          f"mlp_hidden={args.mlp_hidden})", flush=True)

    opt = torch.optim.Adam(model.parameters(), lr=args.lr,
                           weight_decay=args.weight_decay)
    score_scale_sq = args.score_scale ** 2

    for epoch in range(args.epochs):
        model.train()
        np.random.shuffle(train_idx)
        total_loss = 0.0
        nb = 0
        for off in range(0, len(train_idx), args.batch):
            b = train_idx[off:off + args.batch]
            pred = model(pidx_t[:, b], mat_diff_t[b], king_diff_t[b])
            score_mse = F.mse_loss(pred, score_t[b]) * score_scale_sq
            wdl_prob  = (wdl_t[b] + 1.0) * 0.5
            wdl_bce   = F.binary_cross_entropy_with_logits(pred / 400.0, wdl_prob)
            loss = args.lam * score_mse + (1.0 - args.lam) * wdl_bce * 50000.0
            opt.zero_grad()
            loss.backward()
            opt.step()
            total_loss += loss.item()
            nb += 1
        model.eval()
        with torch.no_grad():
            v = model(pidx_t[:, val_idx],
                      mat_diff_t[val_idx], king_diff_t[val_idx])
            val_mse = F.mse_loss(v, score_t[val_idx]).item()
        print(f"epoch {epoch:2d}: train_loss={total_loss/nb:.2f}  "
              f"val_mse={val_mse:.0f}  "
              f"man={model.man_value.item():.1f}  king={model.king_value.item():.1f}",
              flush=True)

    torch.save({
        "state_dict": model.state_dict(),
        "config": {
            "patterns_name": args.patterns,
            "base": 3,
            "embed_dim": args.embed_dim,
            "mlp_hidden": args.mlp_hidden,
            "stm_flip": (not args.no_stm_flip),
        },
    }, args.out)
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, {n_params:,} params)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
