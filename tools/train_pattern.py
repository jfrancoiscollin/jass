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

# v3 Scan-geometry pattern set — 8 vertical-strip patterns × 12 squares.
# Keep in sync with V3_PATTERNS in pattern_network.cpp.
V3_PATTERNS: list[list[int]] = [
    # Top half (rows 1-6)
    [ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27],   # cols 0-1
    [ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28],   # cols 1-2
    [ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29],   # cols 2-3
    [ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30],   # cols 3-4
    # Bottom half (rows 5-10)
    [21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47],
    [22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48],
    [23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49],
    [24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50],
]

# v4 long vertical strips — 8 patterns × 14 squares (7 rows × 2 cols).
# Pushes context window beyond v3's 6 rows. ~38M weights base-3 (~153 MB).
# Keep in sync with V4_PATTERNS in pattern_network.cpp.
V4_PATTERNS: list[list[int]] = [
    # Top half (rows 1-7)
    [ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27, 31, 32],
    [ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28, 32, 33],
    [ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29, 33, 34],
    [ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30, 34, 35],
    # Bottom half (rows 4-10)
    [16, 17, 21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47],
    [17, 18, 22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48],
    [18, 19, 23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49],
    [19, 20, 24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50],
]

PATTERN_SETS = {"v1": V1_PATTERNS, "v2": V2_PATTERNS,
                "v3": V3_PATTERNS, "v4": V4_PATTERNS}

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


def king_pst_features(bbs: np.ndarray) -> np.ndarray:
    """G3a / JPAT v4 — return (50, N) float32 delta-PST feature matrix.

    For each record n, delta[s, n] = (#white_kings at FMJD square s+1)
                                   - (#black_kings at FMJD square 50-s)

    The C++ eval uses king_pst[s-1] for each white king on s and
    -king_pst[50-s] for each black king on s (row-mirror symmetry).
    Folding into a single dot product against the 50-dim PST vector
    keeps the model linear and trainable with the same Adam/L-BFGS path.
    """
    n = bbs.shape[1]
    out = np.zeros((50, n), dtype=np.float32)
    for s in range(50):  # 0..49 (FMJD square = s+1)
        bit_w  = np.uint64(1) << np.uint64(s)
        bit_b  = np.uint64(1) << np.uint64(49 - s)  # row-mirror
        out[s] += ((bbs[1] & bit_w) != 0).astype(np.float32)   # white kings on s+1
        out[s] -= ((bbs[3] & bit_b) != 0).astype(np.float32)   # black kings on 50-s
    return out


def balance_feature(bbs: np.ndarray) -> np.ndarray:
    """G3a / JPAT v4 — L/R skew per record, float32 array of length N.
    Matches C++ compute_skew: per piece, +1 if on a right-side file
    (FMJD col >= 3), -1 if on left-side file (col <= 1), 0 on center
    file (col == 2). White pieces add, black pieces subtract.
    """
    n = bbs.shape[1]
    # Per-square contribution: +1 right (col 3,4), -1 left (col 0,1), 0 center
    contrib = np.zeros(50, dtype=np.int32)
    for s in range(50):
        col = s % 5
        if col < 2:
            contrib[s] = -1
        elif col > 2:
            contrib[s] = +1
    out = np.zeros(n, dtype=np.float32)
    for s in range(50):
        bit = np.uint64(1) << np.uint64(s)
        w   = (((bbs[0] | bbs[1]) & bit) != 0).astype(np.int32) * contrib[s]
        b   = (((bbs[2] | bbs[3]) & bit) != 0).astype(np.int32) * contrib[s]
        out += (w - b).astype(np.float32)
    return out


def _build_king_diag_neighbors() -> list[list[int]]:
    """Mirror of C++ KING_DIAG_NEIGHBORS — for each FMJD square 1..50,
    list of valid diagonally adjacent dark squares (0 to 4 entries)."""
    out: list[list[int]] = []
    for s in range(1, 51):
        r, c = (s - 1) // 5, (s - 1) % 5
        cb = 2 * c + (1 - r % 2)
        nbrs: list[int] = []
        for dr in (-1, +1):
            for dcb in (-1, +1):
                rp, cbp = r + dr, cb + dcb
                if rp < 0 or rp >= 10 or cbp < 0 or cbp >= 10:
                    continue
                if cbp % 2 != (rp + 1) % 2:
                    continue
                cp = (cbp - (1 - rp % 2)) // 2
                nbrs.append(rp * 5 + cp + 1)
        out.append(sorted(nbrs))
    return out


KING_DIAG_NEIGHBORS = _build_king_diag_neighbors()


def king_mobility_feature(bbs: np.ndarray) -> np.ndarray:
    """H4 / JPAT v6 — return per-record float32 mobility values matching
    C++ `compute_king_mobility` : sum over white kings of count(empty
    diag neighbors) minus same for black kings. Sign-flipped by STM at
    the trainer level (white-POV convention)."""
    n = bbs.shape[1]
    occ = bbs[0] | bbs[1] | bbs[2] | bbs[3]
    out = np.zeros(n, dtype=np.float32)
    for s in range(1, 51):
        nbrs = KING_DIAG_NEIGHBORS[s - 1]
        if not nbrs:
            continue
        bit_s = np.uint64(1) << np.uint64(s - 1)
        wk_here = (bbs[1] & bit_s) != 0
        bk_here = (bbs[3] & bit_s) != 0
        if not (wk_here.any() or bk_here.any()):
            continue
        free_count = np.zeros(n, dtype=np.int32)
        for nbr in nbrs:
            bit_n = np.uint64(1) << np.uint64(nbr - 1)
            free_count += ((occ & bit_n) == 0).astype(np.int32)
        out += np.where(wk_here, free_count, 0).astype(np.float32)
        out -= np.where(bk_here, free_count, 0).astype(np.float32)
    return out


def stage_features(bbs: np.ndarray) -> np.ndarray:
    """G3b / JPAT v5 — return per-record float32 stage values in
    [0, STAGE_SIZE]. Matches C++ `compute_stage`:
      phase = wm + bm + 2*(wk + bk)
      stage = clamp(STAGE_SIZE * (40 - phase) / 40, 0, STAGE_SIZE)
    """
    STAGE_SIZE      = 300
    STAGE_OPEN_PHASE = 40
    if hasattr(np, "bitwise_count"):
        popcnt = lambda b: np.bitwise_count(b).astype(np.int32)
    else:
        def popcnt(b):
            x = b.copy()
            x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
            x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
            x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
            return ((x * np.uint64(0x0101010101010101)) >> np.uint64(56)).astype(np.int32)
    wm = popcnt(bbs[0])
    wk = popcnt(bbs[1])
    bm = popcnt(bbs[2])
    bk = popcnt(bbs[3])
    phase = wm + bm + 2 * (wk + bk)
    stage = (STAGE_SIZE * (STAGE_OPEN_PHASE - phase) // STAGE_OPEN_PHASE)
    stage = np.clip(stage, 0, STAGE_SIZE).astype(np.float32)
    return stage


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

    When `extras = True` (G3a / JPAT v4), also include a king PST
    (50-dim weight vector) and a scalar balance L/R parameter.

    The eval is `bias + man_value * (Wmen - Bmen)
              + king_value * (Wkings - Bkings)
              + king_pst · delta_pst(pos)        [G3a only]
              + balance  · skew(pos)             [G3a only]
              + sum_p pattern_p[idx_p(pos)]`

    in white-POV. Initialising man/king to handcrafted-eval-like values
    (~100 / ~300) gives the trainer a reasonable starting point: the
    patterns only have to learn the residual positional corrections
    rather than the absolute piece values from scratch (cf.
    docs/archives/SCAN_ARCHITECTURE_NOTES.md §6).
    """
    def __init__(self, patterns: list[list[int]],
                 base: int = 5,
                 init_man:  float = 100.0,
                 init_king: float = 300.0,
                 extras: bool = False,
                 phase_split: bool = False,
                 mobility: bool = False,
                 mlp_hidden: int = 0):
        super().__init__(patterns, base=base)
        self.man_value  = nn.Parameter(torch.tensor(init_man))
        self.king_value = nn.Parameter(torch.tensor(init_king))
        self.extras     = extras
        self.phase_split = phase_split
        self.mobility    = mobility
        self.mlp_hidden  = mlp_hidden
        if mlp_hidden > 0:
            # JPAT v7 — hybrid MLP head. Per-pattern values → ReLU(hidden) → scalar.
            # Small random init for non-trivial gradient flow.
            n = len(patterns)
            self.mlp_w1 = nn.Parameter(torch.randn(n, mlp_hidden) * 0.01)
            self.mlp_b1 = nn.Parameter(torch.zeros(mlp_hidden))
            self.mlp_w2 = nn.Parameter(torch.randn(mlp_hidden) * 0.01)
            self.mlp_b2 = nn.Parameter(torch.zeros(1))
        if extras:
            self.king_pst = nn.Parameter(torch.zeros(50))
            self.balance  = nn.Parameter(torch.tensor(0.0))
        if mobility:
            # H4 / JPAT v6 — king mobility scalar (MG, EG if phase_split).
            self.mobility_mg = nn.Parameter(torch.tensor(0.0))
            if phase_split:
                self.mobility_eg = nn.Parameter(torch.tensor(0.0))
        if phase_split:
            # G3b / JPAT v5 — EG counterparts of the skeleton. Initialised
            # to MG values so the start state has no phase split (eval =
            # MG everywhere); the trainer then deviates EG from MG as
            # needed. Patterns themselves stay mono-phase in v5.
            self.bias_eg       = nn.Parameter(torch.zeros(1))
            self.man_value_eg  = nn.Parameter(torch.tensor(init_man))
            self.king_value_eg = nn.Parameter(torch.tensor(init_king))
            if extras:
                self.king_pst_eg = nn.Parameter(torch.zeros(50))
                self.balance_eg  = nn.Parameter(torch.tensor(0.0))

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
      * extras (king PST + balance, G3a)  → v4
      * base != 5                          → v3
      * HybridPatternModel                 → v2
      * else                               → v1 (legacy, base=5 implicit)
    """
    is_hybrid    = isinstance(model, HybridPatternModel)
    has_extras   = is_hybrid and getattr(model, "extras", False)
    has_phase    = is_hybrid and getattr(model, "phase_split", False)
    has_mobility = is_hybrid and getattr(model, "mobility", False)
    has_mlp      = is_hybrid and getattr(model, "mlp_hidden", 0) > 0
    base         = model.base
    if has_mlp:
        version = 7
    elif has_mobility:
        version = 6
    elif has_phase:
        version = 5
    elif has_extras:
        version = 4
    elif base != 5:
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
            # v1 has no skeleton; v2+ always write it (0/0 if not hybrid).
            man_int  = int(round(model.man_value.item()))  if is_hybrid else 0
            king_int = int(round(model.king_value.item())) if is_hybrid else 0
            f.write(struct.pack("<i", man_int))              # man_value
            f.write(struct.pack("<i", king_int))             # king_value
        if version >= 3:
            f.write(struct.pack("<B", base))                 # encoding_base
        if version >= 4:
            # G3a / JPAT v4 extras: balance scalar + king_pst[50].
            balance_int = int(round(model.balance.item()))
            f.write(struct.pack("<i", balance_int))          # balance
            pst = model.king_pst.detach().cpu().numpy()
            pst_q = np.round(pst).clip(-2**31, 2**31 - 1).astype(np.int32)
            f.write(pst_q.tobytes())                         # king_pst[50] int32
        if version >= 5:
            # G3b / JPAT v5: EG counterparts of bias/man/king/balance/king_pst.
            bias_eg_i = int(round(model.bias_eg.item()))
            man_eg_i  = int(round(model.man_value_eg.item()))
            king_eg_i = int(round(model.king_value_eg.item()))
            bal_eg_i  = int(round(model.balance_eg.item())) if has_extras else 0
            f.write(struct.pack("<i", bias_eg_i))
            f.write(struct.pack("<i", man_eg_i))
            f.write(struct.pack("<i", king_eg_i))
            f.write(struct.pack("<i", bal_eg_i))
            if has_extras:
                pst_eg   = model.king_pst_eg.detach().cpu().numpy()
                pst_eg_q = np.round(pst_eg).clip(-2**31, 2**31 - 1).astype(np.int32)
            else:
                pst_eg_q = np.zeros(50, dtype=np.int32)
            f.write(pst_eg_q.tobytes())
        if version >= 6:
            # H4 / JPAT v6: king mobility (mg / eg).
            mob_mg_i = int(round(model.mobility_mg.item())) if has_mobility else 0
            mob_eg_i = (int(round(model.mobility_eg.item()))
                        if (has_mobility and has_phase) else 0)
            f.write(struct.pack("<i", mob_mg_i))
            f.write(struct.pack("<i", mob_eg_i))
        if version >= 7:
            # JPAT v7: hybrid MLP head (uint8 hidden + float32 weights).
            h = int(model.mlp_hidden) if has_mlp else 0
            f.write(struct.pack("<B", h))
            if h > 0:
                n = len(patterns)
                w1 = model.mlp_w1.detach().cpu().numpy().astype(np.float32)
                b1 = model.mlp_b1.detach().cpu().numpy().astype(np.float32)
                w2 = model.mlp_w2.detach().cpu().numpy().astype(np.float32)
                b2 = float(model.mlp_b2.detach().cpu().numpy().item())
                # w1 is (n_patterns, h), C++ expects row-major n × h
                assert w1.shape == (n, h)
                f.write(w1.tobytes())
                f.write(b1.tobytes())
                f.write(w2.tobytes())
                f.write(struct.pack("<f", b2))
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

    Rationale (cf. docs/archives/SCAN_METHODOLOGY_GAP.md §G1): the loss
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
    king_pst_t:  torch.Tensor | None,   # G3a extras: (50, N) shaped
    balance_t:   torch.Tensor | None,   # G3a extras: (N,) shaped
    stage_t:     torch.Tensor | None,   # G3b phase split: (N,) shaped
    mobility_t:  torch.Tensor | None,   # H4 mobility: (N,) shaped
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
    extras: bool = False,
    phase_split: bool = False,
    mobility: bool = False,
    mlp_hidden: int = 0,
    optimizer_kind: str = "adam",
    lbfgs_max_iter: int = 20,
    lbfgs_history: int = 10,
    lbfgs_early_stop_patience: int = 5,
    loss_type: str = "mse",
    huber_delta: float = 200.0,
    tag: str = "",
) -> PatternModel:
    """Train one PatternModel and return it. Factored out of `main`
    so the multi-seed wrapper can call it N times and average."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    if hybrid:
        assert mat_diff_t is not None and king_diff_t is not None
        model = HybridPatternModel(patterns, base=base,
                                   init_man=init_man, init_king=init_king,
                                   extras=extras, phase_split=phase_split,
                                   mobility=mobility, mlp_hidden=mlp_hidden)
    else:
        model = PatternModel(patterns, base=base)

    # `score_scale` divides scores before the MSE so the loss isn't
    # dominated by raw centipawn² magnitudes. With scale=1 the loss is
    # identical to the legacy formulation (preserves backward compat).
    score_scale_sq = score_scale * score_scale

    def _forward(idx_slice: np.ndarray) -> torch.Tensor:
        if not hybrid:
            return model(pidx_t[:, idx_slice])
        n = idx_slice.shape[0]
        # Patterns contribute mono-phase in JPAT v5 — same value to mg
        # and eg accumulators (so we compute once and reuse). For JPAT
        # v7 (hybrid MLP head) we also keep the per-pattern values as a
        # (n, P) tensor to feed the MLP.
        num_p = len(model.tables)
        pattern_vals = torch.zeros(n, num_p, dtype=torch.float32)
        for pi, table in enumerate(model.tables):
            pattern_vals[:, pi] = table(pidx_t[pi][idx_slice]).squeeze(-1)
        pat = pattern_vals.sum(dim=1)
        # MG accumulator (skeleton + patterns).
        acc_mg = (model.bias.expand(n).clone() + pat
                  + model.man_value  * mat_diff_t[idx_slice]
                  + model.king_value * king_diff_t[idx_slice])
        if mlp_hidden > 0:
            # JPAT v7 — MLP residual on top of acc_mg (MG-only).
            # pattern_vals : (n, P)  →  hidden : (n, H)  →  out : (n,)
            hidden = torch.relu(pattern_vals @ model.mlp_w1 + model.mlp_b1)
            acc_mg = acc_mg + hidden @ model.mlp_w2 + model.mlp_b2.squeeze()
        if extras:
            assert king_pst_t is not None and balance_t is not None
            acc_mg = (acc_mg
                      + (model.king_pst.unsqueeze(1) * king_pst_t[:, idx_slice]).sum(dim=0)
                      + model.balance * balance_t[idx_slice])
        if mobility:
            assert mobility_t is not None
            acc_mg = acc_mg + model.mobility_mg * mobility_t[idx_slice]
        if not phase_split:
            return acc_mg
        # EG accumulator (G3b / JPAT v5).
        assert stage_t is not None
        acc_eg = (model.bias_eg.expand(n).clone() + pat
                  + model.man_value_eg  * mat_diff_t[idx_slice]
                  + model.king_value_eg * king_diff_t[idx_slice])
        if extras:
            acc_eg = (acc_eg
                      + (model.king_pst_eg.unsqueeze(1) * king_pst_t[:, idx_slice]).sum(dim=0)
                      + model.balance_eg * balance_t[idx_slice])
        if mobility:
            acc_eg = acc_eg + model.mobility_eg * mobility_t[idx_slice]
        stage = stage_t[idx_slice]
        return (acc_mg * (300.0 - stage) + acc_eg * stage) / 300.0

    def _loss(pred: torch.Tensor, idx_slice: np.ndarray) -> torch.Tensor:
        score_batch = score_t[idx_slice]
        wdl_batch   = wdl_t[idx_slice]
        if loss_type == "huber":
            # Robust to outliers : L2 within ±delta cp, L1 beyond. Scan
            # labels have outliers ±30000 (forced-mate scores) that
            # destroy plain MSE fit ; Huber gracefully clips their
            # gradient contribution.
            score_loss = F.huber_loss(pred, score_batch,
                                       delta=huber_delta) * score_scale_sq
        else:
            score_loss = F.mse_loss(pred, score_batch) * score_scale_sq
        wdl_prob  = (wdl_batch + 1.0) * 0.5
        wdl_bce   = F.binary_cross_entropy_with_logits(pred / 400.0, wdl_prob)
        return lam * score_loss + (1.0 - lam) * wdl_bce * 50000.0

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
            if getattr(avg, "extras", False):
                pst_stack = torch.stack([m.king_pst for m in models], dim=0)
                bal_stack = torch.stack([m.balance  for m in models], dim=0)
                avg.king_pst.copy_(pst_stack.mean(dim=0))
                avg.balance.copy_(bal_stack.mean(dim=0))
            if getattr(avg, "phase_split", False):
                be_stack  = torch.stack([m.bias_eg       for m in models], dim=0)
                me_stack  = torch.stack([m.man_value_eg  for m in models], dim=0)
                ke_stack  = torch.stack([m.king_value_eg for m in models], dim=0)
                avg.bias_eg.copy_(be_stack.mean(dim=0))
                avg.man_value_eg.copy_(me_stack.mean(dim=0))
                avg.king_value_eg.copy_(ke_stack.mean(dim=0))
                if getattr(avg, "extras", False):
                    pe_stack = torch.stack([m.king_pst_eg for m in models], dim=0)
                    be2_stack = torch.stack([m.balance_eg  for m in models], dim=0)
                    avg.king_pst_eg.copy_(pe_stack.mean(dim=0))
                    avg.balance_eg.copy_(be2_stack.mean(dim=0))
            if getattr(avg, "mobility", False):
                mob_mg_stack = torch.stack([m.mobility_mg for m in models], dim=0)
                avg.mobility_mg.copy_(mob_mg_stack.mean(dim=0))
                if getattr(avg, "phase_split", False):
                    mob_eg_stack = torch.stack([m.mobility_eg for m in models], dim=0)
                    avg.mobility_eg.copy_(mob_eg_stack.mean(dim=0))
            if getattr(avg, "mlp_hidden", 0) > 0:
                w1_stack = torch.stack([m.mlp_w1 for m in models], dim=0)
                b1_stack = torch.stack([m.mlp_b1 for m in models], dim=0)
                w2_stack = torch.stack([m.mlp_w2 for m in models], dim=0)
                b2_stack = torch.stack([m.mlp_b2 for m in models], dim=0)
                avg.mlp_w1.copy_(w1_stack.mean(dim=0))
                avg.mlp_b1.copy_(b1_stack.mean(dim=0))
                avg.mlp_w2.copy_(w2_stack.mean(dim=0))
                avg.mlp_b2.copy_(b2_stack.mean(dim=0))
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
    p.add_argument("--extras", action="store_true",
                   help="G3a / JPAT v4 : add king PST (50 white-POV weights, "
                        "black uses row-mirror) + scalar balance L/R. "
                        "Requires --hybrid.")
    p.add_argument("--phase-split", action="store_true",
                   help="G3b / JPAT v5 : add MG/EG counterparts for the "
                        "scalar skeleton features (bias / man / king / "
                        "balance / king_pst). Patterns stay mono-phase. "
                        "Stage interpolation in evaluate. Requires "
                        "--hybrid.")
    p.add_argument("--mobility", action="store_true",
                   help="H4 / JPAT v6 : add king mobility feature (count "
                        "of empty diag neighbors per king, white - black). "
                        "1 weight (MG-only) or 2 weights (with --phase-split). "
                        "Requires --hybrid.")
    p.add_argument("--mlp-hidden", type=int, default=0,
                   help="JPAT v7 : add a small MLP head (N patterns → H hidden "
                        "ReLU → 1 output, MG-only residual) on top of the "
                        "linear pattern sum. 0 (default) disables. Try 16 "
                        "for a non-linear combiner. Requires --hybrid.")
    p.add_argument("--pattern-base", type=int, default=5, choices=[3, 5],
                   help="per-square encoding base. 5 = legacy (empty/"
                        "W-man/W-king/B-man/B-king). 3 = D2 Scan-aligned "
                        "(empty/white/black; kings folded with men in "
                        "patterns, handled by king_value skeleton). base=3 "
                        "requires --hybrid (otherwise kings are lost).")
    p.add_argument("--optimizer", choices=["adam", "lbfgs"], default="adam",
                   help="G1 of docs/archives/SCAN_METHODOLOGY_GAP.md. lbfgs runs "
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
    p.add_argument("--loss-type", choices=["mse", "huber"], default="mse",
                   help="score-side loss. huber = robust to outliers (Scan "
                        "labels have outliers ±30000 cp from forced-mate "
                        "scores ; MSE compresses everything, huber preserves "
                        "fit for normal range and L1-clips outliers).")
    p.add_argument("--huber-delta", type=float, default=200.0,
                   help="huber transition point (cp) : L2 within ±delta, L1 "
                        "beyond. Default 200 cp matches typical search-tuned "
                        "eval residuals.")
    args = p.parse_args(argv)
    if args.pattern_base == 3 and not args.hybrid:
        p.error("--pattern-base 3 requires --hybrid (king info would "
                "otherwise be lost; cf. docs/archives/SCAN_ARCHITECTURE_NOTES.md §1)")
    if args.extras and not args.hybrid:
        p.error("--extras (G3a king PST + balance) requires --hybrid")
    if args.phase_split and not args.hybrid:
        p.error("--phase-split (G3b MG/EG skeleton) requires --hybrid")
    if args.mobility and not args.hybrid:
        p.error("--mobility (H4 king mobility) requires --hybrid")
    if args.mlp_hidden > 0 and not args.hybrid:
        p.error("--mlp-hidden requires --hybrid")
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
    # (JPAT v2, cf. docs/archives/SCAN_ARCHITECTURE_NOTES.md §6). Sign-flip for
    # STM=Black so they match the white-POV target sign.
    mat_diff_t  = None
    king_diff_t = None
    king_pst_t  = None
    balance_t   = None
    stage_t     = None
    mobility_t  = None
    if args.hybrid:
        mat_diff, king_diff = material_diffs(bbs)
        mat_diff[stm  == 1] *= -1
        king_diff[stm == 1] *= -1
        mat_diff_t  = torch.from_numpy(mat_diff)
        king_diff_t = torch.from_numpy(king_diff)
        if args.extras:
            # G3a / JPAT v4 — king PST + balance. Same sign-flip for
            # STM=Black (white-POV convention).
            pst = king_pst_features(bbs)  # shape (50, N)
            bal = balance_feature(bbs)    # shape (N,)
            pst[:, stm == 1] *= -1
            bal[stm == 1]    *= -1
            king_pst_t = torch.from_numpy(pst)
            balance_t  = torch.from_numpy(bal)
        if args.phase_split:
            # G3b / JPAT v5 — stage is symmetric under STM (depends only
            # on piece count). No sign-flip needed.
            stage_t = torch.from_numpy(stage_features(bbs))
        if args.mobility:
            # H4 / JPAT v6 — king mobility (white_free - black_free per
            # record). Sign-flip for STM=Black (white-POV).
            mob = king_mobility_feature(bbs)
            mob[stm == 1] *= -1
            mobility_t = torch.from_numpy(mob)

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
        king_pst_t=king_pst_t, balance_t=balance_t,
        stage_t=stage_t, mobility_t=mobility_t,
        train_idx=train_idx, val_idx=val_idx,
        epochs=args.epochs, batch=args.batch, lr=args.lr, lam=args.lam,
        score_scale=args.score_scale, weight_decay=args.weight_decay,
        grad_clip=args.grad_clip, warmup_frac=args.warmup_frac,
        cosine_schedule=args.cosine_schedule,
        hybrid=args.hybrid, init_man=args.init_man, init_king=args.init_king,
        base=args.pattern_base, extras=args.extras,
        phase_split=args.phase_split, mobility=args.mobility,
        mlp_hidden=args.mlp_hidden,
        optimizer_kind=args.optimizer,
        lbfgs_max_iter=args.lbfgs_max_iter,
        lbfgs_history=args.lbfgs_history,
        lbfgs_early_stop_patience=args.lbfgs_early_stop_patience,
        loss_type=args.loss_type,
        huber_delta=args.huber_delta,
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
