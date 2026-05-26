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

# v2 pattern set — 16 patterns × 8 squares, full coverage with overlap.
# Keep in sync with V2_PATTERNS in pattern_network.cpp.
V2_PATTERNS: list[list[int]] = [
    [ 1,  2,  6,  7, 11, 12, 16, 17],
    [ 2,  3,  7,  8, 12, 13, 17, 18],
    [ 3,  4,  8,  9, 13, 14, 18, 19],
    [ 4,  5,  9, 10, 14, 15, 19, 20],
    [11, 12, 16, 17, 21, 22, 26, 27],
    [12, 13, 17, 18, 22, 23, 27, 28],
    [13, 14, 18, 19, 23, 24, 28, 29],
    [14, 15, 19, 20, 24, 25, 29, 30],
    [21, 22, 26, 27, 31, 32, 36, 37],
    [22, 23, 27, 28, 32, 33, 37, 38],
    [23, 24, 28, 29, 33, 34, 38, 39],
    [24, 25, 29, 30, 34, 35, 39, 40],
    [31, 32, 36, 37, 41, 42, 46, 47],
    [32, 33, 37, 38, 42, 43, 47, 48],
    [33, 34, 38, 39, 43, 44, 48, 49],
    [34, 35, 39, 40, 44, 45, 49, 50],
]

PATTERN_SETS = {"v1": V1_PATTERNS, "v2": V2_PATTERNS}

# International draughts board is symmetric under horizontal flip. With
# squares numbered 1..50, 5 per row, 10 rows, the mirror swaps positions
# within each row of 5: 1↔5, 2↔4, 3↔3, 6↔10, 7↔9, 8↔8, … This doubles
# the effective training set when applied as augmentation, and is the
# cheapest data-side fix listed in PATTERN_ROADMAP.md Phase 1.
def _mirror_square(s: int) -> int:
    row = (s - 1) // 5
    col = (s - 1) % 5
    return row * 5 + (4 - col) + 1


# Bit-level mirror map: original bit b (0..49) → mirrored bit. Used to
# rewrite the four bitboards in one O(50) pass per record. Built once.
SQUARE_MIRROR = np.array(
    [_mirror_square(s + 1) - 1 for s in range(50)], dtype=np.uint64
)


def mirror_bitboards(bbs: np.ndarray) -> np.ndarray:
    """Apply horizontal mirror to a (4, N) array of uint64 bitboards.
    Returns a new array of the same shape with each set bit relocated
    to its mirror square."""
    out = np.zeros_like(bbs)
    for b in range(50):
        mask = np.uint64(1) << np.uint64(b)
        dst  = np.uint64(1) << np.uint64(SQUARE_MIRROR[b])
        set_in_src = (bbs & mask) != 0
        out |= dst * set_in_src.astype(np.uint64)
    return out


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


def material_diffs(bbs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (mat_diff, king_diff) float32 arrays of length N, where
    mat_diff[i]  = popcount(Wmen[i])   - popcount(Bmen[i])
    king_diff[i] = popcount(Wkings[i]) - popcount(Bkings[i]).

    These are the D1 structural skeleton features (cf. JPAT v2 spec)."""
    def popcnt(bb: np.ndarray) -> np.ndarray:
        # numpy >=2.0 ships np.bitwise_count; older versions need a fallback.
        if hasattr(np, "bitwise_count"):
            return np.bitwise_count(bb).astype(np.int32)
        # Manual SWAR popcount over uint64.
        b = bb.copy()
        b = b - ((b >> np.uint64(1)) & np.uint64(0x5555555555555555))
        b = (b & np.uint64(0x3333333333333333)) + ((b >> np.uint64(2)) & np.uint64(0x3333333333333333))
        b = (b + (b >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
        return ((b * np.uint64(0x0101010101010101)) >> np.uint64(56)).astype(np.int32)
    wm = popcnt(bbs[0])
    wk = popcnt(bbs[1])
    bm = popcnt(bbs[2])
    bk = popcnt(bbs[3])
    return (wm - bm).astype(np.float32), (wk - bk).astype(np.float32)


def pattern_indices(bbs: np.ndarray, patterns: list[list[int]],
                    base: int = 5) -> np.ndarray:
    """For each position N × each pattern P, compute the base bucket
    index. Returns int64 array of shape (P, N).

    `base = 5` (legacy / JPAT v1/v2): empty/W-man/W-king/B-man/B-king
                                      mapped to 0/1/2/3/4.
    `base = 3` (D2 / JPAT v3, Scan-aligned): empty/white/black mapped
                                             to 0/1/2 (king ≡ man here;
                                             handled by king_value
                                             skeleton instead)."""
    if base not in (3, 5):
        raise ValueError(f"unsupported base {base}; must be 3 or 5")
    n_patterns = len(patterns)
    n_positions = bbs.shape[1]
    out = np.zeros((n_patterns, n_positions), dtype=np.int64)
    for pi, sqs in enumerate(patterns):
        mult = 1
        for sq in sqs:
            bit = sq - 1
            mask = np.uint64(1) << np.uint64(bit)
            wm = (bbs[0] & mask) != 0
            wk = (bbs[1] & mask) != 0
            bm = (bbs[2] & mask) != 0
            bk = (bbs[3] & mask) != 0
            state = np.zeros(n_positions, dtype=np.int64)
            if base == 5:
                state[wm] = 1
                state[wk] = 2
                state[bm] = 3
                state[bk] = 4
            else:  # base == 3
                state[wm | wk] = 1
                state[bm | bk] = 2
            out[pi] += state * mult
            mult *= base
    return out


class PatternModel(nn.Module):
    """Pure-pattern model (legacy, JPAT v1 if base=5).

    For the D1 hybrid model that adds material/king skeleton features,
    see `HybridPatternModel` below.

    `base` selects the per-square encoding (5 = legacy, 3 = Scan-aligned
    D2). Embedding tables are sized `base ** K` per pattern.
    """
    def __init__(self, patterns: list[list[int]], base: int = 5):
        super().__init__()
        if base not in (3, 5):
            raise ValueError(f"unsupported base {base}; must be 3 or 5")
        self.base = base
        self.tables = nn.ModuleList([
            nn.Embedding(base ** len(p), 1) for p in patterns
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


class HybridPatternModel(PatternModel):
    """D1 hybrid (JPAT v2 if base=5, v3 if base=3): patterns + material/king
    count skeleton.

    The eval is `bias + man_value * (Wmen - Bmen)
              + king_value * (Wkings - Bkings)
              + sum_p pattern_p[idx_p(pos)]`

    in white-POV. Initialising man/king to handcrafted-eval-like values
    (~100 / ~300) gives the trainer a reasonable starting point: the
    patterns only have to learn the residual positional corrections
    rather than the absolute piece values from scratch (cf.
    docs/SCAN_ARCHITECTURE_NOTES.md §6).
    """
    def __init__(self, patterns: list[list[int]],
                 base: int = 5,
                 init_man:  float = 100.0,
                 init_king: float = 300.0):
        super().__init__(patterns, base=base)
        self.man_value  = nn.Parameter(torch.tensor(init_man))
        self.king_value = nn.Parameter(torch.tensor(init_king))

    def forward(self, indices: torch.Tensor,
                mat_diff: torch.Tensor,
                king_diff: torch.Tensor) -> torch.Tensor:
        s = (self.bias.expand(indices.shape[1]).clone()
             + self.man_value  * mat_diff
             + self.king_value * king_diff)
        for pi, table in enumerate(self.tables):
            s = s + table(indices[pi]).squeeze(-1)
        return s


def save_jpat(model: PatternModel, patterns: list[list[int]], out_path: Path) -> None:
    """Quantise float32 weights to int32 centipawn and write JPAT.

    Version is auto-selected:
      * base != 5             → v3 (always, since base must be recorded)
      * HybridPatternModel    → v2 (or v3 if base != 5)
      * else                  → v1 (legacy, pure-pattern, base=5 implicit)
    """
    is_hybrid = isinstance(model, HybridPatternModel)
    base      = model.base
    if base != 5:
        version = 3
    elif is_hybrid:
        version = 2
    else:
        version = 1
    with out_path.open("wb") as f:
        f.write(b"JPAT")
        f.write(struct.pack("<I", version))                  # version
        f.write(struct.pack("<I", len(patterns)))            # num_patterns
        bias_int = int(round(model.bias.item()))
        f.write(struct.pack("<i", bias_int))                 # bias
        if version >= 2:
            # v1 has no skeleton; v2/v3 always write it (0/0 if not hybrid).
            man_int  = int(round(model.man_value.item()))  if is_hybrid else 0
            king_int = int(round(model.king_value.item())) if is_hybrid else 0
            f.write(struct.pack("<i", man_int))              # man_value
            f.write(struct.pack("<i", king_int))             # king_value
        if version >= 3:
            f.write(struct.pack("<B", base))                 # encoding_base
        for pi, sqs in enumerate(patterns):
            k = len(sqs)
            f.write(struct.pack("<B", k))                    # num_squares
            f.write(bytes(sqs))                              # squares
            weights = model.tables[pi].weight.detach().cpu().numpy().flatten()
            quantised = np.round(weights).clip(-2**31, 2**31 - 1).astype(np.int32)
            f.write(quantised.tobytes())


def _train_lbfgs(
    *,
    model: PatternModel,
    train_idx: np.ndarray,
    val_idx:   np.ndarray,
    epochs: int,
    lr: float,
    grad_clip: float,
    l2: float,
    lbfgs_max_iter: int,
    lbfgs_history: int,
    early_stop_patience: int,
    score_t: torch.Tensor,
    pidx_t: torch.Tensor,
    hybrid: bool,
    mat_diff_t,
    king_diff_t,
    forward,
    loss,
    tag: str,
) -> "PatternModel":
    """G1 path: full-batch L-BFGS on the convex pattern loss.

    Rationale (cf. docs/SCAN_METHODOLOGY_GAP.md §G1): the loss
    `λ·MSE + (1-λ)·BCE` is globally convex in pattern weights (linear
    embedding lookups + scalar bias/skeleton params). Adam on minibatches
    oscillates around the minimum on this kind of objective; L-BFGS with
    strong-Wolfe line search converges in dozens of full-batch iterations.
    Each `opt.step(closure)` call performs up to `lbfgs_max_iter` inner
    line-search iterations, so `epochs` here is the OUTER iteration count.

    Manual L2 regularisation: PyTorch LBFGS doesn't support weight_decay,
    but the convex objective combined with no regularisation can overfit
    sharply on small / WDL-only datasets (smoke test on master games:
    train loss ↘, val MSE ↗ x20 across 10 iters). L2 is added inside the
    closure when l2 > 0.

    Early stopping: if val MSE doesn't improve over `early_stop_patience`
    consecutive outer iterations, training halts and the best-val
    checkpoint is restored.
    """
    opt = torch.optim.LBFGS(
        model.parameters(),
        lr=lr,
        max_iter=lbfgs_max_iter,
        history_size=lbfgs_history,
        line_search_fn="strong_wolfe",
    )

    import copy
    best_val   = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    stale      = 0

    for epoch in range(epochs):
        model.train()

        def closure():
            opt.zero_grad()
            pred = forward(train_idx)
            l    = loss(pred, train_idx)
            if l2 > 0:
                reg = sum((p * p).sum() for p in model.parameters())
                l = l + 0.5 * l2 * reg
            l.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            return l

        train_loss = opt.step(closure).item()

        # Validation
        model.eval()
        with torch.no_grad():
            val_pred = forward(val_idx)
            val_mse  = F.mse_loss(val_pred, score_t[val_idx]).item()
        extra = ""
        if hybrid:
            extra = (f"  man={model.man_value.item():6.1f}"
                     f"  king={model.king_value.item():6.1f}")
        marker = ""
        if val_mse < best_val:
            best_val   = val_mse
            best_state = copy.deepcopy(model.state_dict())
            stale      = 0
            marker     = " *"
        else:
            stale += 1
        print(f"{tag}iter {epoch:2d}: train_loss={train_loss:10.2f}  "
              f"val_mse={val_mse:10.2f}{extra}{marker}", flush=True)
        if stale >= early_stop_patience > 0:
            print(f"{tag}early stop: no val improvement for "
                  f"{early_stop_patience} iters (best val_mse={best_val:.2f})",
                  flush=True)
            break

    # Restore best-val checkpoint so the saved JPAT reflects the
    # generalising model rather than the last (potentially overfit) one.
    model.load_state_dict(best_state)
    return model


def train_one(
    *,
    patterns: list[list[int]],
    pidx_t: torch.Tensor,
    score_t: torch.Tensor,
    wdl_t:   torch.Tensor,
    mat_diff_t:  torch.Tensor | None,   # D1 hybrid: required when hybrid=True
    king_diff_t: torch.Tensor | None,
    train_idx: np.ndarray,
    val_idx:   np.ndarray,
    seed: int,
    epochs: int,
    batch: int,
    lr: float,
    lam: float,
    score_scale: float,
    weight_decay: float,
    grad_clip: float,
    warmup_frac: float,
    cosine_schedule: bool,
    hybrid: bool = False,
    init_man:  float = 100.0,
    init_king: float = 300.0,
    base: int = 5,
    optimizer_kind: str = "adam",
    lbfgs_max_iter: int = 20,
    lbfgs_history: int = 10,
    lbfgs_early_stop_patience: int = 5,
    tag: str = "",
) -> PatternModel:
    """Train one PatternModel and return it. Factored out of `main`
    so the multi-seed wrapper can call it N times and average."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    if hybrid:
        assert mat_diff_t is not None and king_diff_t is not None
        model = HybridPatternModel(patterns, base=base,
                                   init_man=init_man, init_king=init_king)
    else:
        model = PatternModel(patterns, base=base)

    # `score_scale` divides scores before the MSE so the loss isn't
    # dominated by raw centipawn² magnitudes. With scale=1 the loss is
    # identical to the legacy formulation (preserves backward compat).
    score_scale_sq = score_scale * score_scale

    def _forward(idx_slice: np.ndarray) -> torch.Tensor:
        if hybrid:
            return model(pidx_t[:, idx_slice],
                         mat_diff_t[idx_slice],
                         king_diff_t[idx_slice])
        return model(pidx_t[:, idx_slice])

    def _loss(pred: torch.Tensor, idx_slice: np.ndarray) -> torch.Tensor:
        score_batch = score_t[idx_slice]
        wdl_batch   = wdl_t[idx_slice]
        score_mse = F.mse_loss(pred, score_batch) * score_scale_sq
        wdl_prob  = (wdl_batch + 1.0) * 0.5
        wdl_bce   = F.binary_cross_entropy_with_logits(pred / 400.0, wdl_prob)
        return lam * score_mse + (1.0 - lam) * wdl_bce * 50000.0

    if optimizer_kind == "lbfgs":
        return _train_lbfgs(
            model=model, train_idx=train_idx, val_idx=val_idx,
            epochs=epochs, lr=lr, grad_clip=grad_clip,
            l2=weight_decay,
            lbfgs_max_iter=lbfgs_max_iter, lbfgs_history=lbfgs_history,
            early_stop_patience=lbfgs_early_stop_patience,
            score_t=score_t, pidx_t=pidx_t, hybrid=hybrid,
            mat_diff_t=mat_diff_t, king_diff_t=king_diff_t,
            forward=_forward, loss=_loss, tag=tag,
        )

    # ---- Adam path (legacy minibatch) ----
    opt = torch.optim.Adam(model.parameters(), lr=lr,
                           weight_decay=weight_decay)

    # LR schedule. By default (warmup_frac=0 and cosine_schedule=False)
    # the LR is constant — matches the legacy behaviour.
    steps_per_epoch = (len(train_idx) + batch - 1) // batch
    total_steps     = steps_per_epoch * epochs
    warmup_steps    = max(1, int(total_steps * warmup_frac)) if warmup_frac > 0 else 0
    decay_steps     = max(1, total_steps - warmup_steps)
    use_schedule    = warmup_steps > 0 or cosine_schedule

    def lr_factor(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        if not cosine_schedule:
            return 1.0
        progress = (step - warmup_steps) / decay_steps
        progress = min(max(progress, 0.0), 1.0)
        return 0.5 * (1.0 + np.cos(np.pi * progress))

    scheduler = (torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda=lr_factor)
                 if use_schedule else None)

    for epoch in range(epochs):
        model.train()
        np.random.shuffle(train_idx)
        total_loss = 0.0
        nb = 0
        for off in range(0, len(train_idx), batch):
            batch_idx = train_idx[off:off + batch]
            pred = _forward(batch_idx)
            loss = _loss(pred, batch_idx)
            opt.zero_grad()
            loss.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()
            if scheduler is not None:
                scheduler.step()
            total_loss += loss.item()
            nb += 1

        # Validation.
        model.eval()
        with torch.no_grad():
            val_pred = _forward(val_idx)
            val_mse  = F.mse_loss(val_pred, score_t[val_idx]).item()
        lr_now = opt.param_groups[0]["lr"]
        extra = ""
        if hybrid:
            extra = (f"  man={model.man_value.item():6.1f}"
                     f"  king={model.king_value.item():6.1f}")
        print(f"{tag}epoch {epoch:2d}: train_loss={total_loss/nb:10.2f}  "
              f"val_mse={val_mse:10.2f}  lr={lr_now:.2e}{extra}", flush=True)

    return model


def average_models(models: list[PatternModel]) -> PatternModel:
    """Return a new PatternModel whose weights are the per-tensor mean
    across `models`. Multi-seed averaging is the cheapest variance
    reduction trick for sparse pattern weights (cf. PATTERN_ROADMAP §1)."""
    if len(models) == 1:
        return models[0]
    import copy
    avg = copy.deepcopy(models[0])
    with torch.no_grad():
        for ti, table in enumerate(avg.tables):
            stack = torch.stack([m.tables[ti].weight for m in models], dim=0)
            table.weight.copy_(stack.mean(dim=0))
        bias_stack = torch.stack([m.bias for m in models], dim=0)
        avg.bias.copy_(bias_stack.mean(dim=0))
        if isinstance(avg, HybridPatternModel):
            man_stack  = torch.stack([m.man_value  for m in models], dim=0)
            king_stack = torch.stack([m.king_value for m in models], dim=0)
            avg.man_value.copy_(man_stack.mean(dim=0))
            avg.king_value.copy_(king_stack.mean(dim=0))
    return avg


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
    p.add_argument("--patterns", choices=list(PATTERN_SETS.keys()), default="v1",
                   help="which pattern set (v1=8×4, v2=16×8 full-coverage)")

    # Phase 1 (cf. PATTERN_ROADMAP §1 / Phase 1 ROADMAP) — all default
    # to off / 1.0 so legacy callers keep identical behaviour.
    p.add_argument("--symmetry", action="store_true",
                   help="augment dataset by horizontal mirror (free ×2 data, "
                        "draughts board is L-R symmetric)")
    p.add_argument("--score-scale", type=float, default=1.0,
                   help="divide score-MSE by this scale² so it doesn't drown "
                        "the BCE term (try 0.01 for v2 sparse patterns)")
    p.add_argument("--weight-decay", type=float, default=0.0,
                   help="L2 weight decay passed to Adam")
    p.add_argument("--grad-clip", type=float, default=0.0,
                   help="clip gradient norm to this value (0 = off)")
    p.add_argument("--warmup-frac", type=float, default=0.0,
                   help="fraction of total steps used for linear LR warmup")
    p.add_argument("--cosine-schedule", action="store_true",
                   help="apply cosine LR decay after warmup")
    p.add_argument("--num-seeds", type=int, default=1,
                   help="train N independent runs and average their weights "
                        "(seeds = --seed, --seed+1, …)")
    p.add_argument("--hybrid", action="store_true",
                   help="D1 hybrid model (JPAT v2): patterns + material/king "
                        "skeleton. Trainable man_value/king_value scalars "
                        "added to the white-POV sum.")
    p.add_argument("--init-man",  type=float, default=100.0,
                   help="initial man_value (cp per (Wmen - Bmen) diff)")
    p.add_argument("--init-king", type=float, default=300.0,
                   help="initial king_value (cp per (Wkings - Bkings) diff)")
    p.add_argument("--pattern-base", type=int, default=5, choices=[3, 5],
                   help="per-square encoding base. 5 = legacy (empty/"
                        "W-man/W-king/B-man/B-king). 3 = D2 Scan-aligned "
                        "(empty/white/black; kings folded with men in "
                        "patterns, handled by king_value skeleton). base=3 "
                        "requires --hybrid (otherwise kings are lost).")
    p.add_argument("--optimizer", choices=["adam", "lbfgs"], default="adam",
                   help="G1 of docs/SCAN_METHODOLOGY_GAP.md. lbfgs runs "
                        "full-batch L-BFGS on the convex loss (much better "
                        "fit than Adam for linear pattern models). "
                        "Ignores --weight-decay (LBFGS doesn't support it) "
                        "and --warmup-frac / --cosine-schedule.")
    p.add_argument("--lbfgs-max-iter",  type=int, default=20,
                   help="LBFGS inner line-search iterations per outer step")
    p.add_argument("--lbfgs-history",   type=int, default=10,
                   help="LBFGS history size (memory of past gradients)")
    p.add_argument("--lbfgs-early-stop-patience", type=int, default=5,
                   help="stop LBFGS if val MSE hasn't improved for N "
                        "outer iters (0 = disabled). Restores best-val "
                        "checkpoint on exit. Critical because LBFGS without "
                        "regularisation can overfit aggressively on small "
                        "or WDL-only datasets.")
    args = p.parse_args(argv)
    if args.pattern_base == 3 and not args.hybrid:
        p.error("--pattern-base 3 requires --hybrid (king info would "
                "otherwise be lost; cf. docs/SCAN_ARCHITECTURE_NOTES.md §1)")
    if args.optimizer == "lbfgs" and args.weight_decay > 0:
        print(f"note: --weight-decay={args.weight_decay} applied as manual "
              "L2 inside the LBFGS closure (PyTorch LBFGS doesn't support "
              "weight_decay natively)", flush=True)

    patterns = PATTERN_SETS[args.patterns]

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    print(f"loading {args.data}...", flush=True)
    bbs, stm, score, wdl = load_jnnw(args.data, args.max_records)
    n = bbs.shape[1]
    print(f"  {n} records loaded", flush=True)

    if args.symmetry:
        print("augmenting with horizontal mirror (×2)...", flush=True)
        bbs_m = mirror_bitboards(bbs)
        # Mirror preserves STM, score and wdl (L-R is a pure spatial
        # symmetry that doesn't change colour-to-move or outcome).
        bbs   = np.concatenate([bbs, bbs_m],   axis=1)
        stm   = np.concatenate([stm, stm.copy()])
        score = np.concatenate([score, score.copy()])
        wdl   = np.concatenate([wdl, wdl.copy()])
        n = bbs.shape[1]
        print(f"  augmented dataset: {n} records", flush=True)

    print(f"encoding pattern indices ({len(patterns)} patterns, "
          f"base={args.pattern_base})...", flush=True)
    pidx = pattern_indices(bbs, patterns, base=args.pattern_base)
    print(f"  done, shape={pidx.shape}", flush=True)

    # D1 hybrid: extract material / king count diffs from bitboards.
    # These are the structural skeleton features added to the patterns
    # (JPAT v2, cf. docs/SCAN_ARCHITECTURE_NOTES.md §6). Sign-flip for
    # STM=Black so they match the white-POV target sign.
    mat_diff_t  = None
    king_diff_t = None
    if args.hybrid:
        mat_diff, king_diff = material_diffs(bbs)
        mat_diff[stm  == 1] *= -1
        king_diff[stm == 1] *= -1
        mat_diff_t  = torch.from_numpy(mat_diff)
        king_diff_t = torch.from_numpy(king_diff)

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

    common_kwargs = dict(
        patterns=patterns, pidx_t=pidx_t, score_t=score_t, wdl_t=wdl_t,
        mat_diff_t=mat_diff_t, king_diff_t=king_diff_t,
        train_idx=train_idx, val_idx=val_idx,
        epochs=args.epochs, batch=args.batch, lr=args.lr, lam=args.lam,
        score_scale=args.score_scale, weight_decay=args.weight_decay,
        grad_clip=args.grad_clip, warmup_frac=args.warmup_frac,
        cosine_schedule=args.cosine_schedule,
        hybrid=args.hybrid, init_man=args.init_man, init_king=args.init_king,
        base=args.pattern_base,
        optimizer_kind=args.optimizer,
        lbfgs_max_iter=args.lbfgs_max_iter,
        lbfgs_history=args.lbfgs_history,
        lbfgs_early_stop_patience=args.lbfgs_early_stop_patience,
    )

    models: list[PatternModel] = []
    for s in range(args.num_seeds):
        seed = args.seed + s
        tag = f"[seed {seed}] " if args.num_seeds > 1 else ""
        if args.num_seeds > 1:
            print(f"=== run {s+1}/{args.num_seeds} (seed {seed}) ===", flush=True)
        models.append(train_one(seed=seed, tag=tag, **common_kwargs))

    if args.num_seeds > 1:
        print(f"averaging {args.num_seeds} models...", flush=True)
    model = average_models(models)

    # Final validation on the averaged model so we report a number
    # that matches what gets saved to disk.
    model.eval()
    with torch.no_grad():
        if args.hybrid:
            val_pred = model(pidx_t[:, val_idx],
                             mat_diff_t[val_idx],
                             king_diff_t[val_idx])
        else:
            val_pred = model(pidx_t[:, val_idx])
        val_mse  = F.mse_loss(val_pred, score_t[val_idx]).item()
    extra = ""
    if args.hybrid:
        extra = (f"  man={model.man_value.item():.1f}"
                 f"  king={model.king_value.item():.1f}")
    print(f"final (saved) val_mse={val_mse:10.2f}{extra}", flush=True)

    save_jpat(model, patterns, args.out)
    sz = args.out.stat().st_size
    print(f"wrote {args.out} ({sz} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
