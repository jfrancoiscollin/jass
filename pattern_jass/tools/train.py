#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Linear pattern-jass regression trainer.

Reads a JNNW master dataset (jass core format, cf src/main.cpp:220),
extracts per-sample pattern-jass indices, fits y_pred = Σ_p w[off_p + idx_p]
by L-BFGS minimisation of MSE + L2, then writes int32 weights to disk.

Output binary format (PJTW = "Pattern-Jass-Trained-Weights") :
   uint32_t magic     = 0x57544A50  ("PJTW")
   uint32_t version   = 1
   uint32_t count     = TOTAL_BUCKETS (472392)
   uint32_t scale     = quantisation factor (centi-piece units)
   int32_t  weights[count]

Target convention :
   * label = WDL from STM POV (-1 / 0 / +1)
   * eval_pred(b) = Σ w[idx[i]] computed on "black POV" indices, then
     sign-flipped if stm=white. Same convention as Othello POC.

  → For training we compute the prediction in "black POV" and the
    target is the WDL re-projected to black POV : `wdl_black =
    wdl_stm * (1 if stm==0 else -1)`. Wait : stm=0 = white-to-move
    (cf src/main.cpp:222). So black-POV wdl = wdl_stm if stm==1 else
    -wdl_stm.
"""

import argparse
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master_loader
# Geometry source: by default the repo's patterns.py, but JASS_PATTERNS_DIR (a path
# OUTSIDE the git tree) takes precedence. The job runner periodically resets the
# working tree to origin/main, which would silently revert a startup-emitted variant
# geometry mid-run; pointing at an external copy makes the active geometry reset-proof
# (and lets parallel jobs each pin their own pattern set without committing to main).
_pgd = os.environ.get("JASS_PATTERNS_DIR")
if _pgd:
    sys.path.insert(0, _pgd)
import patterns

WEIGHTS_MAGIC   = 0x57544A50  # "PJTW" little-endian
WEIGHTS_VERSION = 1

# Full Scan-style structured eval (v3). The dense "extras" vector is produced
# by `jass --dump-eval-features` and MUST match src/scan_eval.hpp NUM_EXTRAS
# and its layout exactly (king PST 0..99, men counts 100/101, mobility
# 102/103, balance 104/105). The trainer consumes that dump verbatim — there
# is no second implementation here, so the playable eval and the training
# features are identical by construction.
WEIGHTS_VERSION_V3 = 3
# High bits OR'd into the version word self-describe the eval so the C++ loader
# rejects a wrong binary/weights pairing loudly (cf src/scan_eval.hpp): SELFDESC
# marks a king-aware-era file, KING marks men|kings occupancy. Must match
# scan_eval.hpp V_SELFDESC_BIT / V_KING_BIT.
PJTW_SELFDESC_BIT  = 0x200
PJTW_KING_BIT      = 0x100
EVAL_NUM_EXTRAS    = 106


def _pjtw_version(base: int, king: bool) -> int:
    """base version (3/4) OR the self-describing king/men marker bits."""
    return base | PJTW_SELFDESC_BIT | (PJTW_KING_BIT if king else 0)


def build_sparse_X(cols: np.ndarray, n_features: int) -> sp.csr_matrix:
    """Each row = exactly NUM_PATTERNS non-zeros at `cols[i]`, value 1."""
    n, npp = cols.shape
    data    = np.ones(n * npp, dtype=np.float64)
    indices = cols.reshape(-1)
    indptr  = np.arange(0, n * npp + 1, npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, n_features), dtype=np.float64)


CF_SIZE  = 12
CF_HALF  = (3 ** CF_SIZE - 1) // 2          # 265720 = max |signed index|
CF_BUCKETS = CF_HALF + 1                     # 265721 canonical buckets / pattern


def colorfold_maps():
    """Maps from the unsigned base-3 config index u (0..3^12-1, cell∈{0=empty,
    1=black,2=white}) to its COLOUR-ANTISYMMETRIC canonical bucket and sign:
      signed(u) = Σ_k sgn(cell_k)·3^k  with black→+1, white→-1, empty→0
      U2C[u] = |signed(u)| ∈ [0, CF_HALF]   U2S[u] = ±1
    A config and its colour-swap (black↔white) map to the SAME bucket with
    opposite sign → one shared antisymmetric weight."""
    n = 3 ** CF_SIZE
    u = np.arange(n, dtype=np.int64)
    tmp = u.copy(); signed = np.zeros(n, dtype=np.int64)
    for k in range(CF_SIZE):
        cell = tmp % 3; tmp //= 3
        signed += np.where(cell == 1, 1, np.where(cell == 2, -1, 0)) * (3 ** k)
    U2C = np.abs(signed).astype(np.int64)
    U2S = np.where(signed >= 0, 1, -1).astype(np.int64)
    return U2C, U2S


def build_sparse_X_phased(cols: np.ndarray, wmg: np.ndarray, weg: np.ndarray,
                          total_buckets: int,
                          signs: np.ndarray | None = None) -> sp.csr_matrix:
    """Phase-split design matrix : 2× columns [mg block | eg block]. Each row
    has its NUM_PATTERNS buckets in the mg block (value wmg[i]) AND in the eg
    block at col+total_buckets (value weg[i]). prediction = wmg·(w_mg·φ) +
    weg·(w_eg·φ) = the game-stage interpolation the C++ eval must reproduce.
    `signs` (n, NUM_PATTERNS, ±1) multiplies the entries for --color-fold's
    antisymmetric weights (default all +1)."""
    n, npp = cols.shape
    mg_idx = cols
    eg_idx = cols + total_buckets
    indices = np.concatenate([mg_idx, eg_idx], axis=1).reshape(-1)
    sg = np.ones((n, npp), dtype=np.float32) if signs is None else signs.astype(np.float32)
    mg_data = np.repeat(wmg[:, None], npp, axis=1) * sg
    eg_data = np.repeat(weg[:, None], npp, axis=1) * sg
    # float32 design matrix : halves memory (critical for multi-M datasets);
    # ample precision for a least-squares fit on cp-scale targets.
    data    = np.concatenate([mg_data, eg_data], axis=1).reshape(-1).astype(np.float32)
    indptr  = np.arange(0, n * 2 * npp + 1, 2 * npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, 2 * total_buckets), dtype=np.float32)


def piece_count(ds) -> np.ndarray:
    """Total pieces per record (men + kings, both sides), 0..40 — the game
    stage proxy. Vectorised popcount of the OR of the 4 bitboards."""
    allbb = (ds.white_men | ds.white_kings | ds.black_men | ds.black_kings)
    bits  = np.unpackbits(allbb.view(np.uint8)).reshape(ds.n_records, 64)
    return bits.sum(axis=1)


def phase_wmg(pc: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Midgame weight from piece count, ramp 0 (≤lo) → 1 (≥hi). Must match the
    C++ scan_eval::phase_wmg EXACTLY. lo=0,hi=40 reproduces the legacy pc/40."""
    denom = (hi - lo) if hi > lo else 1.0
    return np.clip((pc - lo) / denom, 0.0, 1.0)


# Phase boundaries by piece count, IDENTICAL to tools/game_autopsy.py and
# tools/phase_proxy.py so the training reweighting lines up with the microscopes
# that measure where the eval bleeds. Used by --phase-weight to over/under-weight
# rows of a given phase in the loss (the loop's "densification" knob : Scan proves
# a linear eval CAN play endgames, so if ours bleeds there the fix is data weight /
# label depth, not non-linearity — cf jobs 0249/0250/0251/0252).
PHASE_BOUNDS = [("opening", 30, 99), ("midgame", 22, 29), ("late-mid", 15, 21),
                ("endgame", 8, 14), ("deep-eg", 0, 7)]


def parse_phase_weight(spec: str) -> dict:
    """Parse "endgame=3,deep-eg=4" → {'endgame':3.0,'deep-eg':4.0}. Unlisted
    phases default to 1.0. Raises on an unknown phase name or non-positive mult."""
    names = {n for n, _lo, _hi in PHASE_BOUNDS}
    out = {}
    for tok in spec.split(','):
        tok = tok.strip()
        if not tok:
            continue
        if '=' not in tok:
            raise SystemExit(f'--phase-weight: bad token {tok!r} (want name=mult)')
        name, val = tok.split('=', 1)
        name = name.strip()
        if name not in names:
            raise SystemExit(f'--phase-weight: unknown phase {name!r} '
                             f'(known: {sorted(names)})')
        m = float(val)
        if m <= 0:
            raise SystemExit(f'--phase-weight: {name} mult must be > 0, got {m}')
        out[name] = m
    return out


def phase_multiplier(pc: np.ndarray, spec: dict) -> np.ndarray:
    """Per-row multiplier (1.0 default) from a parsed phase-weight spec."""
    pw = np.ones(len(pc), dtype=np.float64)
    for name, lo, hi in PHASE_BOUNDS:
        m = spec.get(name, 1.0)
        if m != 1.0:
            pw[(pc >= lo) & (pc <= hi)] = m
    return pw



def king_onehot_block(black_kings: np.ndarray,
                      white_kings: np.ndarray) -> sp.csr_matrix:
    """100 extra linear features (king PST) in the fixed black-POV
    orientation matching the men-pattern features : black_kings one-hot on
    squares 0..49, white_kings on 50..99. Lets the fit-check see whether
    explicit KING-position info (which the men-only patterns are blind to)
    helps fit the Scan−handcrafted residual."""
    n = len(black_kings)
    sq = np.arange(50, dtype=np.uint64)
    bk = ((black_kings[:, None] >> sq) & 1).astype(np.float64)   # (n, 50)
    wk = ((white_kings[:, None] >> sq) & 1).astype(np.float64)
    return sp.csr_matrix(np.hstack([bk, wk]))                    # (n, 100)


def load_feature_file(path: str, n_expected: int,
                      standardise: bool = True) -> np.ndarray:
    """Load a "FEAT" file from `jass --dump-features` / `--dump-eval-features`.
    Returns (n, K) float64. For FIT-CHECK use (standardise=True) the columns
    are z-standardised so the L2 penalty is scale-fair vs the 0/1 pattern
    features. For a PLAYABLE eval (standardise=False) the RAW values are kept
    so the learned weights apply to the exact same feature values the C++
    eval (ScanEvalNetwork) computes — standardising here would silently
    rescale the eval at inference."""
    raw = Path(path).read_bytes()
    if raw[:4] != b'FEAT':
        raise SystemExit(f'{path}: not a FEAT file')
    cnt, k = struct.unpack_from('<II', raw, 4)
    if cnt != n_expected:
        raise SystemExit(f'feature count {cnt} != data {n_expected}')
    arr = np.frombuffer(raw, dtype='<f4', offset=12,
                        count=cnt * k).reshape(cnt, k).astype(np.float64)
    if not standardise:
        return arr
    std = arr.std(axis=0)
    std[std == 0] = 1.0
    return (arr - arr.mean(axis=0)) / std


def load_quiet_flags(path: str, n_expected: int) -> np.ndarray:
    """Load a "QIET" sidecar from `jass --dump-quiet-flags` : one uint8 per
    record, 1 = quiet (side to move has no mandatory capture), 0 = tactical.
    Returns a boolean mask of length n_expected."""
    raw = Path(path).read_bytes()
    if raw[:4] != b'QIET':
        raise SystemExit(f'{path}: not a QIET file')
    cnt = struct.unpack_from('<I', raw, 4)[0]
    if cnt != n_expected:
        raise SystemExit(f'quiet-flag count {cnt} != data {n_expected}')
    flags = np.frombuffer(raw, dtype=np.uint8, offset=8, count=cnt)
    return flags.astype(bool)


def build_extras_phased(extras: np.ndarray, wmg: np.ndarray,
                        weg: np.ndarray) -> sp.csr_matrix:
    """Phase-split dense extras : [ext*wmg | ext*weg]. Row prediction
    contributes wmg·(w_ext_mg·x) + weg·(w_ext_eg·x) — the same MG/EG
    interpolation ScanEvalNetwork::evaluate() applies to the extras."""
    # float32 throughout : the dense (n, 2·NUM_EXTRAS) intermediate is the peak
    # allocation at multi-M rows — float32 halves it (~8GB→4GB at 4.7M).
    ex = extras.astype(np.float32, copy=False)
    mg = ex * wmg[:, None].astype(np.float32)
    eg = ex * weg[:, None].astype(np.float32)
    return sp.csr_matrix(np.hstack([mg, eg]), dtype=np.float32)


def write_weights_v3(path: Path, pat_mg: np.ndarray, pat_eg: np.ndarray,
                     ext_mg: np.ndarray, ext_eg: np.ndarray,
                     scale: int, king: bool = False) -> None:
    """PJTW v3 : magic, version=3 (+ self-desc/king marker bits), scale, n_pat,
    n_ext, then int32 weights ordered [pat_mg | pat_eg | ext_mg | ext_eg]
    (cf src/scan_eval.hpp). `king` records men|kings occupancy so a wrong
    binary/weights pairing is rejected at load."""
    n_pat = len(pat_mg)
    n_ext = len(ext_mg)
    assert len(pat_eg) == n_pat and len(ext_eg) == n_ext
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIIII', WEIGHTS_MAGIC,
                            _pjtw_version(WEIGHTS_VERSION_V3, king),
                            scale, n_pat, n_ext))
        for blk in (pat_mg, pat_eg, ext_mg, ext_eg):
            f.write(blk.astype('<i4').tobytes())


WEIGHTS_VERSION_V4 = 4


def fit_pattern_fm(idx_tr, r_tr, idx_val, r_val, H, k, l2_fm, max_iter, seed):
    """Pattern-only Factorization-Machine term, fit to the LINEAR RESIDUAL
    (boosting : linear first, FM explains the interactions it missed). Each of
    the NUM_PATTERNS active buckets is HASHED to H slots and gets a rank-k
    latent vector ; the pairwise term is ½ Σ_f [ (Σ_p V_{p,f})² − Σ_p V_{p,f}² ].
    Returns V (NP*H, k) float64 and prints val_mse(linear) vs (linear+FM)."""
    NP = patterns.NUM_PATTERNS
    rng = np.random.default_rng(seed)
    St = ((idx_tr % H) + np.arange(NP) * H).astype(np.int64)   # (n,NP) slots
    Sv = ((idx_val % H) + np.arange(NP) * H).astype(np.int64)
    SLOT = NP * H

    def predict(V, S):
        A = np.zeros((S.shape[0], k))
        Bsq = np.zeros((S.shape[0], k))
        for f in range(k):
            vf = V[:, f][S]                       # (n,NP)
            A[:, f] = vf.sum(1)
            Bsq[:, f] = (vf * vf).sum(1)
        return 0.5 * (A * A - Bsq).sum(1), A

    def loss_grad(theta):
        V = theta.reshape(SLOT, k)
        pred, A = predict(V, St)
        diff = pred - r_tr
        N = len(r_tr)
        loss = 0.5 * float(diff @ diff) / N + 0.5 * l2_fm * float(theta @ theta)
        r = diff / N
        gV = np.zeros((SLOT, k))
        flat = St.ravel()
        for f in range(k):
            vf = V[:, f][St]                      # (n,NP)
            contrib = ((r * A[:, f])[:, None] - r[:, None] * vf).ravel()
            # bincount scatter-add (far faster than np.add.at at M-row scale).
            gV[:, f] = np.bincount(flat, weights=contrib, minlength=SLOT)
        return loss, (gV + l2_fm * V).ravel()

    th0 = rng.standard_normal(SLOT * k) * 0.01
    t0 = time.time()
    res = minimize(loss_grad, th0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter, 'maxcor': 5})
    V = res.x.reshape(SLOT, k)
    fmv, _ = predict(V, Sv)
    mse_lin = float(np.mean(r_val ** 2))
    mse_fm = float(np.mean((r_val - fmv) ** 2))
    red = 100 * (mse_lin - mse_fm) / mse_lin if mse_lin else 0.0
    print(f'FM : rank={k} hash={H}  val resid_mse {mse_lin:.4f} → {mse_fm:.4f} '
          f'({red:+.1f}%)  ({time.time()-t0:.1f}s)')
    return V


def write_weights_v4(path: Path, pat_mg, pat_eg, ext_mg, ext_eg, scale,
                     V, H, k, king: bool = False):
    """PJTW v4 : the full v3 block (version field = 4 + self-desc/king marker)
    then an FM section : uint32 fm_rank, uint32 fm_hash, uint32 fm_npat,
    float32 V[fm_npat*H*k] (row-major slot-major : slot s = p*H + (bucket%H),
    then k factors)."""
    n_pat, n_ext = len(pat_mg), len(ext_mg)
    NP = patterns.NUM_PATTERNS
    assert V.shape == (NP * H, k)
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIIII', WEIGHTS_MAGIC,
                            _pjtw_version(WEIGHTS_VERSION_V4, king),
                            scale, n_pat, n_ext))
        for blk in (pat_mg, pat_eg, ext_mg, ext_eg):
            f.write(blk.astype('<i4').tobytes())
        f.write(struct.pack('<III', k, H, NP))
        f.write(V.astype('<f4').tobytes())


def train_lbfgs(X: sp.csr_matrix, y: np.ndarray, l2: float,
                max_iter: int, prior: np.ndarray = None,
                anchor_l2=0.0, logistic: bool = False, sw: np.ndarray = None):
    """Fit by L-BFGS. Default = least-squares (resid = X@w - y). With
    `logistic=True` (Scan's actual objective) the prediction X@w is a LOGIT and
    the loss is the cross-entropy against `y` interpreted as a target PROBABILITY
    in [0,1] (win=1, draw=0.5, loss=0) — i.e. logistic regression over the
    pattern/extra features on game outcomes. `prior`/`anchor_l2` add an L2 pull
    toward a prior (anti-forgetting / material pinning) ; anchor_l2=0 → pure.
    `sw` (per-row, mean≈1) re-weights the DATA term only (phase densification) —
    the anchor/L2 stay unweighted (regularisers, not data)."""
    XT = X.T            # CSC view sharing X's data — no copy (was .tocsr() = a
                        # full duplicate, ~doubling memory on multi-M datasets)
    a = np.asarray(anchor_l2, dtype=np.float64)
    anchored = prior is not None and bool(np.any(a > 0.0))

    def loss_and_grad(w):
        z = X @ w
        if logistic:
            # Numerically-stable sigmoid cross-entropy. d/dz = sigmoid(z) - y.
            p = 0.5 * (np.tanh(0.5 * z) + 1.0)            # = sigmoid(z)
            eps = 1e-12
            ce = -(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))
            resid = p - y
        else:
            resid = z - y
            ce = 0.5 * resid * resid
        if sw is not None:
            loss = float(np.dot(sw, ce)) / len(y)
            resid = sw * resid
        else:
            loss = float(np.sum(ce)) / len(y)
        loss += 0.5 * l2 * float(np.dot(w, w))
        grad = (XT @ resid) / len(y) + l2 * w
        if anchored:
            d = w - prior
            loss += 0.5 * float(np.sum(a * d * d))   # scalar or per-column
            grad += a * d
        return loss, grad

    # Warm-start at the prior when anchoring (faster, stays in its basin).
    w0 = prior.copy() if anchored else np.zeros(X.shape[1], dtype=np.float64)
    # maxcor caps the L-BFGS history : its internal storage is ~(2·maxcor+5)·n
    # float64. At n=42.5M (40-pattern v5) the default maxcor=10 is ~8GB on its
    # own → OOM once the design matrix is added. maxcor=5 halves it with
    # negligible convergence cost for this least-squares fit.
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter, 'maxcor': 5})
    return res.x, float(res.fun), int(res.nit)


def train_lbfgs_chunked(build_fn, tr_idx, y_all, l2, max_iter,
                        logistic, n_cols, batch, sw_all=None):
    """Memory-bounded L-BFGS : the SAME full-batch gradient as train_lbfgs, but
    the design is rebuilt per `batch`-row chunk inside the objective so the dense
    phased extras (the peak allocation, ~2GB/M rows) never materialise for the
    whole set. Lets the fit scale to 10-40M rows on a fixed RAM budget — same
    optimum (the gradient is exact, only the assembly is streamed). Pure L2 only
    (anchors/freq-reg index the whole table and are unsupported here). `sw_all`
    (per-row, mean≈1 over tr_idx) re-weights the data term (phase densification)."""
    N = len(tr_idx); eps = 1e-12

    def loss_and_grad(w):
        cs = 0.0
        grad = np.zeros(n_cols, dtype=np.float64)
        for i in range(0, N, batch):
            sel = tr_idx[i:i + batch]
            Xc = build_fn(sel)                       # chunk design (csr)
            yc = y_all[sel]
            z = Xc @ w
            if logistic:
                p = 0.5 * (np.tanh(0.5 * z) + 1.0)
                ce = -(yc * np.log(p + eps) + (1.0 - yc) * np.log(1.0 - p + eps))
                resid = p - yc
            else:
                resid = z - yc
                ce = 0.5 * resid * resid
            if sw_all is not None:
                swc = sw_all[sel]
                cs += float(np.dot(swc, ce))
                resid = swc * resid
            else:
                cs += float(np.sum(ce))
            grad += Xc.T @ resid                      # accumulate XT@(sw·resid)
        loss = cs / N + 0.5 * l2 * float(np.dot(w, w))
        grad = grad / N + l2 * w
        return loss, grad

    w0 = np.zeros(n_cols, dtype=np.float64)
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter, 'maxcor': 5})
    return res.x, float(res.fun), int(res.nit)


def lowmem_z(Xpat, extras, wmg, weg, w, PAT_N, E):
    """Prediction z = phased-pattern part (Xpat is already wmg/weg-scaled) + the
    phased-extras part computed ON THE FLY from raw extras (n,E) — so the dense
    (n,2E) extras design is never materialised. w = [pat_mg|pat_eg|ext_mg|ext_eg]."""
    w_pat = w[:2 * PAT_N]
    w_emg = w[2 * PAT_N:2 * PAT_N + E]
    w_eeg = w[2 * PAT_N + E:]
    return Xpat @ w_pat + wmg * (extras @ w_emg) + weg * (extras @ w_eeg)


def train_lbfgs_lowmem(Xpat, extras, wmg, weg, y, l2, max_iter,
                       logistic, PAT_N, E, sw=None):
    """Memory-efficient FULL-BATCH L-BFGS : same objective as train_lbfgs, but the
    dense phased extras (the (n,2E) peak, ~2GB/M) is never built — its contribution
    is computed on the fly from raw extras (n,E). Only the compact phased PATTERN
    sparse (n×64 nnz) is kept. Handles ~20M rows on 32GB. Converges to the same
    (convex) optimum up to float32 design-rounding (the matvecs differ in FP order
    from the full hstacked design, so w is equal only to low-order digits, not bit-
    identical). Pure L2 only. `sw` (per-row, mean≈1) re-weights the data term."""
    XpT = Xpat.T
    n_cols = 2 * PAT_N + 2 * E
    N = len(y); eps = 1e-12
    ex = extras.astype(np.float32, copy=False)
    wmg = wmg.astype(np.float64, copy=False); weg = weg.astype(np.float64, copy=False)

    def loss_and_grad(w):
        z = lowmem_z(Xpat, ex, wmg, weg, w, PAT_N, E)
        if logistic:
            p = 0.5 * (np.tanh(0.5 * z) + 1.0)
            ce = -(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))
            resid = p - y
        else:
            resid = z - y
            ce = 0.5 * resid * resid
        if sw is not None:
            loss = float(np.dot(sw, ce)) / N
            resid = sw * resid
        else:
            loss = float(np.sum(ce)) / N
        loss += 0.5 * l2 * float(np.dot(w, w))
        g_pat = XpT @ resid
        # g_ext = ex.T @ (resid·phase) == (resid·phase) @ ex, but the latter keeps
        # ex C-contiguous (the transpose-matvec is strided and ~3× slower).
        g_emg = (resid * wmg) @ ex
        g_eeg = (resid * weg) @ ex
        grad = np.concatenate([np.asarray(g_pat), g_emg, g_eeg]) / N + l2 * w
        return loss, grad

    w0 = np.zeros(n_cols, dtype=np.float64)
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter, 'maxcor': 5})
    return res.x, float(res.fun), int(res.nit)


def material_anchor(n_cols: int, TB: int, E: int, strength: float,
                    man_pu: float = 1.0, king_pu: float = 3.0):
    """Per-column anchor that pins the MATERIAL extras to sane piece-unit
    values, breaking the men-count↔patterns collinearity that scrambled the
    sign of material in the standalone fit (cf 0151). Column order is
    [pat_mg | pat_eg | ext_mg | ext_eg]; extras layout matches scan_eval.hpp:
    bk-PST 0..49, wk-PST 50..99, black_men 100, white_men 101 (mob/bal 102-105
    left free). Black-POV: black material positive, white negative.

    Returns (prior, anchor) float arrays of length n_cols (0 everywhere except
    the material columns, which get `strength` and their target value)."""
    prior  = np.zeros(n_cols, dtype=np.float64)
    anchor = np.zeros(n_cols, dtype=np.float64)
    ext_mg0 = 2 * TB           # first ext_mg column
    ext_eg0 = 2 * TB + E       # first ext_eg column
    for base in (ext_mg0, ext_eg0):
        # men material
        prior[base + 100] = +man_pu;  anchor[base + 100] = strength   # black men
        prior[base + 101] = -man_pu;  anchor[base + 101] = strength   # white men
        # king material (PST one-hots) — kings are NOT in patterns, so this is
        # the only king signal; pin every square to ±king_pu.
        for sq in range(50):
            prior[base + sq]      = +king_pu;  anchor[base + sq]      = strength
            prior[base + 50 + sq] = -king_pu;  anchor[base + 50 + sq] = strength
    return prior, anchor


def load_v3_weights_float(path: str):
    """Read a PJTW v3 file into a float weight vector aligned to the
    [pat_mg | pat_eg | ext_mg | ext_eg] design-matrix column order, plus its
    (scale, n_pat, n_ext). Used as the anchor prior for fine-tuning."""
    raw = Path(path).read_bytes()
    magic, ver, scale, n_pat, n_ext = struct.unpack_from('<IIIII', raw, 0)
    if magic != WEIGHTS_MAGIC or ver != WEIGHTS_VERSION_V3:
        raise SystemExit(f'{path}: not a PJTW v3 file (magic/ver)')
    total = 2 * (n_pat + n_ext)
    arr = np.frombuffer(raw, dtype='<i4', offset=20, count=total).astype(np.float64)
    return arr / float(scale), int(scale), int(n_pat), int(n_ext)


def write_weights(path: Path, w_int32: np.ndarray, scale: int,
                  version: int = WEIGHTS_VERSION) -> None:
    # version 1 = mono-phase (count = TOTAL_BUCKETS) ; version 2 = phase-split
    # (count = 2×TOTAL_BUCKETS, [mg | eg] ; stage = piece count / 40).
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHTS_MAGIC, version,
                            len(w_int32), scale))
        f.write(w_int32.astype('<i4').tobytes())


def train_scan_eval(args):
    """Train the full Scan-style phase-split structured eval → PJTW v3.

    Feature vector per position (all interpolated MG/EG by piece count) :
      [ men patterns (8×12 ternary, sparse) | extras (dense, raw) ]
    where extras = material + king PST + mobility + balance, dumped by
    `jass --dump-eval-features` (single source of truth shared with the C++
    eval). Standalone : the target is the score itself (no skeleton residual).
    """
    if not args.eval_features_file:
        raise SystemExit('--scan-eval requires --eval-features-file '
                         '(raw extras from `jass --dump-eval-features`)')
    if args.skeleton_data:
        print('note: --skeleton-data ignored under --scan-eval '
              '(standalone eval, target = score)')

    print(f'loading JNNW {args.data}')
    t0 = time.time()
    ds = master_loader.load(args.data, max_records=args.max_records)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    if getattr(args, 'king_patterns', False):
        print('extracting pattern indices (PIECE-PRESENCE : men|kings, king-aware)')
        idx = patterns.extract_indices(ds.black_men | ds.black_kings,
                                       ds.white_men | ds.white_kings)
    else:
        print('extracting pattern indices (men only)')
        idx = patterns.extract_indices(ds.black_men, ds.white_men)
    # cols/signs/PAT_BUCKETS depend on the symmetry mode (--rot-fold > --color-fold > none).
    cf_U2C = cf_U2S = None       # set for --color-fold expand
    rf_canon = rf_sign = None    # set for --rot-fold expand (full (NP,NB) maps)
    NP = patterns.NUM_PATTERNS
    _full = getattr(args, 'full_fold', False)
    _trans = getattr(args, 'trans_fold', False) or _full
    _refl = getattr(args, 'refl_fold', False) or _full
    if getattr(args, 'rot_fold', False) or _trans or _refl:
        import symmetry
        rf_canon, rf_sign = symmetry.build_canon(translate=_trans, reflect=_refl)
        cols = rf_canon[np.arange(NP)[None, :], idx]               # (n,32) canonical 17M-space col
        cf_signs = rf_sign[np.arange(NP)[None, :], idx].astype(np.float32)
        PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN                 # canonical space = 17M index space
        nused = int(np.unique(rf_canon.ravel()).size)
        bricks = 'color+rot' + ('+translation' if _trans else '') + ('+reflection' if _refl else '')
        print(f'sym-fold [{bricks}] : {nused:,} distinct weights '
              f'(17M -> {nused:,}, {patterns.TOTAL_BUCKETS/max(nused,1):.2f}x) ; antisymmetric')
    elif getattr(args, 'color_fold', False):
        cf_U2C, cf_U2S = colorfold_maps()
        canon = cf_U2C[idx]                                         # (n,32) in [0,CF_HALF]
        cf_signs = cf_U2S[idx].astype(np.float32)                  # (n,32) ±1
        PAT_BUCKETS = CF_BUCKETS
        cols = canon + (np.arange(NP, dtype=np.int64) * PAT_BUCKETS)[None, :]
        print(f'color-fold : signed-canonical, {PAT_BUCKETS} buckets/pattern '
              f'(17M -> {PAT_BUCKETS*NP:,}) ; antisymmetric weights')
    else:
        cf_signs = None
        PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN
        cols = patterns.flat_feature_columns(idx)

    print(f'loading raw extras {args.eval_features_file}')
    extras = load_feature_file(args.eval_features_file, ds.n_records,
                               standardise=False)
    # The C++ NUM_EXTRAS can change with build flags (e.g. -DJASS_ENDGAME_FEATURES
    # makes it 110). The dump self-describes its width, so adapt to it rather than
    # hardcode 106. Material/anchor indices (100/101) are unchanged in any layout.
    global EVAL_NUM_EXTRAS
    if extras.shape[1] != EVAL_NUM_EXTRAS:
        print(f'  note: extras K={extras.shape[1]} (default {EVAL_NUM_EXTRAS}) '
              f'→ adapting to the dump width')
        EVAL_NUM_EXTRAS = int(extras.shape[1])
    print(f'  extras shape {extras.shape}  '
          f'(mean mob b/w={extras[:, 102].mean():.1f}/{extras[:, 103].mean():.1f})')

    # Standalone target (STM-POV), reprojected to black-POV. Default = the
    # Scan teacher score (distillation) ; --target wdl fits the game outcome
    # ternary {-1,0,1} instead (Scan-style logistic-ish, least-squares here).
    if args.target == 'wdl':
        # WDL {-1,0,1} scaled to piece-units so the target lives on the same
        # scale as the score eval (a win ≈ +wdl_scale piece-units). Lets the
        # anti-forgetting anchor toward a score-distilled champion stay
        # consistent (self-play loop) instead of being swamped by scale.
        target_stm = ds.wdl.astype(np.float64) * args.wdl_scale
        n_pos = int((ds.wdl > 0).sum()); n_neg = int((ds.wdl < 0).sum())
        n_zero = int((ds.wdl == 0).sum())
        print(f'target=wdl  pos={n_pos} neg={n_neg} zero={n_zero} '
              f'({n_zero/ds.n_records*100:.1f}% draws)  wdl_scale={args.wdl_scale}')
    else:
        clipped = np.clip(ds.score.astype(np.float64), -args.score_clip, args.score_clip)
        target_stm = clipped / 100.0
        print(f'target=score  clipped±{int(args.score_clip)}cp / 100  '
              f'std={target_stm.std():.3f}')
    y_black = np.where(ds.stm == 1, target_stm, -target_stm)

    # Scan recipe : logistic regression on game OUTCOMES. The eval score (X@w)
    # is a logit ; the target is the win-probability in black-POV (win=1,
    # draw=0.5, loss=0). Overrides the target/loss above. The output is in logit
    # units (not piece-units) — ranking-preserving for play; the material anchor
    # is disabled (it pins to piece-units, which would fight the logit scale).
    logistic = (getattr(args, 'loss', 'ls') == 'logistic')
    if logistic and getattr(args, 'target', 'wdl') == 'prob':
        # Conversion-gradient target : score field holds a STM-POV win-probability
        # in [0,1] (×10000), written by `jass --egdb-mtc-relabel` — WDL {0,0.5,1}
        # for most positions, MTC-graded in the endgame. Reproject to black-POV.
        prob_stm = np.clip(ds.score.astype(np.float64) / 10000.0, 0.0, 1.0)
        y_black = np.where(ds.stm == 1, prob_stm, 1.0 - prob_stm)
        graded = int(((prob_stm > 0.0) & (prob_stm < 1.0) & (prob_stm != 0.5)).sum())
        print(f'loss=LOGISTIC on PROB target (score/10000)  graded(non-0/0.5/1)={graded}'
              f'  mean={y_black.mean():.3f} std={y_black.std():.3f}')
    elif logistic:
        wdl_black = np.where(ds.stm == 1, ds.wdl.astype(np.float64),
                             -ds.wdl.astype(np.float64))
        y_black = (wdl_black + 1.0) * 0.5            # {-1,0,1} → {0,0.5,1}
        np_ = int((ds.wdl > 0).sum()); nn = int((ds.wdl < 0).sum())
        nz = int((ds.wdl == 0).sum())
        print(f'loss=LOGISTIC on WDL outcomes  win={np_} draw={nz} loss={nn} '
              f'({100*nz/ds.n_records:.1f}% draws)')

    # Game stage : sharpenable ramp (matches scan_eval::phase_wmg).
    pc  = np.minimum(piece_count(ds), 40).astype(np.float64)
    wmg = phase_wmg(pc, args.phase_lo, args.phase_hi)
    weg = 1.0 - wmg
    print(f'phase : piece-count mean={pc.mean():.1f}  wmg mean={wmg.mean():.3f}'
          f'  (ramp {args.phase_lo}/{args.phase_hi})')

    # Row selection : drop extreme teacher scores (the ±9989 "won/lost"
    # verdicts whose squared loss dominates the least-squares fit and poisons
    # it — cf the score-drop breakthrough) and optionally restrict to quiet
    # (non-capture) positions. Both filters AND together; the train/val split
    # is then drawn from the kept rows only.
    n = ds.n_records
    # --score-drop : DROP rows whose |raw score| exceeds the threshold (the
    # ±9989 "won/lost" Scan verdicts) instead of clipping them. In least-squares
    # an extreme target dominates the loss even after a ±5000 clip (5000²=25M vs
    # ~90K for a normal ±300 position), so ~2% of extremes poison the fit (cf
    # 0169: dropping them took val_mse 38.7→1.8 and play 0.42→0.83). 0 = keep.
    # Row selection : drop extreme teacher scores (score-drop) and optionally
    # restrict to quiet (non-capture) positions. Both filters AND together; the
    # split is drawn from the kept rows only.
    keep = np.ones(n, dtype=bool)
    if getattr(args, 'score_drop', 0) and args.score_drop > 0:
        sd = np.abs(ds.score.astype(np.float64)) <= args.score_drop
        keep &= sd
        print(f'score-drop : keep |score|<={int(args.score_drop)}cp → '
              f'{int(sd.sum())}/{n} ({100*sd.mean():.1f}%)')
    if args.quiet_flags_file:
        q = load_quiet_flags(args.quiet_flags_file, n)
        keep &= q
        print(f'quiet-only : keep quiet positions → '
              f'{int(q.sum())}/{n} ({100*q.mean():.1f}%)')
    kept = np.flatnonzero(keep)
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(kept)
    n_val = int(len(kept) * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    TB = PAT_BUCKETS * patterns.NUM_PATTERNS   # 17M (men-only) or 8.5M (--color-fold)

    # --- optional collision-free dense PRUNE of the pattern table ---------------
    # Build a remap bucket(0..TB) -> slot from the TRAIN split: occurring buckets
    # get slots 1..K, everything else shares slot 0 (fallback). Training then runs
    # over PAT_N = K+1 pattern columns instead of TB; we scatter back to the full
    # table at output (so the .pjtw / C++ eval are unchanged).
    # LOSSLESS ONLY at --prune-min-visits=1 : then every train bucket is kept, slot 0
    # is never activated in train, its weight stays 0, and the deployed eval (pruned
    # buckets -> 0) equals the full-table fit. With min_visits>=2 the 1..(min-1)-visit
    # buckets pool into slot 0, which gets a non-zero fitted weight; the deploy DROPS
    # it (those buckets play as 0), so the deployed eval differs slightly from the
    # trained model — surfaced by the WARNING below.
    PAT_N = TB
    dcols = cols
    remap = None
    if getattr(args, 'prune', False):
        if args.anchor_weights or args.material_anchor > 0 or \
           getattr(args, 'freq_reg', 0) > 0 or args.fm_rank > 0:
            raise SystemExit('--prune is incompatible with anchors/freq-reg/fm '
                             '(those index the full 17M table).')
        ccounts = np.bincount(cols[tr_idx].ravel(), minlength=TB)
        keep = np.flatnonzero(ccounts >= args.prune_min_visits)
        # order kept buckets by frequency desc → common buckets get the low slots
        keep = keep[np.argsort(ccounts[keep])[::-1]]
        K = len(keep)
        remap = np.zeros(TB, dtype=np.int64)      # 0 = fallback/unseen
        remap[keep] = np.arange(1, K + 1)
        dcols = remap[cols]                        # (n,32) in [0, K]
        PAT_N = K + 1
        fb_tr = float((dcols[tr_idx] == 0).mean())
        print(f'prune : keep {K:,} buckets (>= {args.prune_min_visits} visits) '
              f'-> {2*PAT_N:,} pattern cols vs {2*TB:,}  ({TB/max(PAT_N,1):.1f}× fewer); '
              f'train fallback={100*fb_tr:.3f}%')
        if args.prune_min_visits > 1 and fb_tr > 0:
            print(f'  WARNING: --prune-min-visits={args.prune_min_visits}>1 → the fallback '
                  f'slot absorbs {100*fb_tr:.2f}% of train activations (low-count buckets) but '
                  f'is DROPPED at deploy → the played eval differs slightly from the trained '
                  f'model. Use --prune-min-visits=1 for a lossless prune.', file=sys.stderr)

    def build_pat(sel):
        sg = cf_signs[sel] if cf_signs is not None else None
        return build_sparse_X_phased(dcols[sel], wmg[sel], weg[sel], PAT_N, sg)

    def build(sel):
        xe = build_extras_phased(extras[sel], wmg[sel], weg[sel])
        return sp.hstack([build_pat(sel), xe], format='csr')   # [pat_mg|pat_eg|ext_mg|ext_eg]

    lm = bool(getattr(args, 'lowmem', False))
    mb = int(getattr(args, 'minibatch', 0) or 0)
    if lm and mb:
        print('warning: --lowmem set → --minibatch ignored (lowmem is full-batch; '
              'it keeps the whole pattern sparse + raw extras in RAM, not chunked)',
              file=sys.stderr)
    y_tr, y_val = y_black[tr_idx], y_black[val_idx]
    n_cols = 2 * PAT_N + 2 * EVAL_NUM_EXTRAS
    Xpat_tr = Xpat_val = ex_tr = ex_val = None
    if lm:
        # memory-efficient full-batch : keep only the compact phased PATTERN sparse
        # + raw extras ; the dense (n,2E) extras design is computed on the fly.
        Xpat_tr, Xpat_val = build_pat(tr_idx), build_pat(val_idx)
        ex_tr, ex_val = extras[tr_idx], extras[val_idx]
        X_tr = X_val = None
    else:
        X_val = build(val_idx)
        X_tr  = None if mb > 0 else build(tr_idx)   # minibatch streams tr in chunks
    print(f'design : {n_cols} columns (2×{PAT_N} pat + 2×{EVAL_NUM_EXTRAS} ext)'
          f'{"  [LOWMEM full-batch, on-the-fly extras]" if lm else (f"  [MINIBATCH {mb:,} rows/chunk]" if mb else "")}')
    # Anchors COMBINE (per-column): a uniform anti-forgetting pull toward a v3
    # prior (--anchor-weights, keeps a TD/WDL re-fit from drifting away from a
    # known-good model — cf the 0149 collapse) PLUS a strong per-column pin of
    # the material extras to sane piece-units (--material-anchor, cf 0151). The
    # material overlay overrides the uniform anchor on the material columns.
    prior  = np.zeros(n_cols, dtype=np.float64)
    anchor = np.zeros(n_cols, dtype=np.float64)
    if args.anchor_weights:
        wprior, pscale, pnp, pne = load_v3_weights_float(args.anchor_weights)
        if pnp != TB or pne != EVAL_NUM_EXTRAS:
            raise SystemExit(f'anchor shape ({pnp},{pne}) != ({TB},{EVAL_NUM_EXTRAS})')
        prior = np.asarray(wprior, dtype=np.float64).copy()
        anchor[:] = args.anchor_l2
        print(f'anti-forget : L2={args.anchor_l2} toward prior {args.anchor_weights}')
    if args.material_anchor > 0:
        mprior, manchor = material_anchor(n_cols, TB, EVAL_NUM_EXTRAS,
                                          args.material_anchor,
                                          man_pu=args.man_pu, king_pu=args.king_pu)
        mask = manchor > 0
        prior[mask] = mprior[mask]; anchor[mask] = manchor[mask]
        print(f'material-anchor : strength={args.material_anchor} '
              f'man=±{args.man_pu} king=±{args.king_pu} '
              f'(pinned columns={int(mask.sum())})')
    if getattr(args, 'freq_reg', 0) and args.freq_reg > 0:
        # Frequency-weighted L2 on the PATTERN buckets : per-column anchor toward
        # 0 = strength / (visits + 1). Rare (under-trained) buckets — the ones
        # that give garbage on the deep positions search reaches (cf 0188's depth
        # degradation) — are shrunk HARD toward 0 (neutral), while well-trained
        # common buckets keep their signal. The targeted, collision-free version
        # of the (failed) bucket-hashing idea. Prior stays 0 for pattern columns.
        counts = np.bincount(cols[tr_idx].ravel(),
                             minlength=TB).astype(np.float64)
        fanch = args.freq_reg / (counts + 1.0)            # (TB,)
        anchor[0:TB]      = np.maximum(anchor[0:TB],      fanch)   # pat_mg
        anchor[TB:2 * TB] = np.maximum(anchor[TB:2 * TB], fanch)   # pat_eg
        rare = int((counts <= 2).sum())
        print(f'freq-reg : strength={args.freq_reg}  buckets≤2 visits='
              f'{rare}/{TB} ({100*rare/TB:.1f}%)  '
              f'anchor(rare)≈{args.freq_reg/3:.3g}  anchor(1k visits)≈'
              f'{args.freq_reg/1000:.2g}')
    use_anchor = (not logistic) and bool(np.any(anchor > 0.0))

    # --phase-weight : per-row data-term multiplier by game phase (densification
    # knob). Normalised so the mean weight over the TRAIN rows is 1.0 → the L2 and
    # the loss scale stay directly comparable to an unweighted run; only the
    # RELATIVE emphasis across phases changes. Validation stays unweighted (we
    # still want the true held-out fit), but we also print a per-phase val_mse so
    # the effect on the endgame is visible.
    sw_tr = sw_all = None
    pw_spec = parse_phase_weight(getattr(args, 'phase_weight', '') or '')
    if pw_spec:
        if len(tr_idx) == 0:
            raise SystemExit('--phase-weight: empty train split (check --val-frac / '
                             'score-drop / quiet filters)')
        pw = phase_multiplier(pc, pw_spec)                  # (n,)
        scale_sw = len(tr_idx) / float(pw[tr_idx].sum())    # → mean over tr = 1
        sw_all = pw * scale_sw
        sw_tr = sw_all[tr_idx]
        # report the shift in effective mass per phase (where the fit now "looks")
        msg = []
        for name, lo, hi in PHASE_BOUNDS:
            sel = (pc[tr_idx] >= lo) & (pc[tr_idx] <= hi)
            if sel.any():
                raw = 100.0 * sel.mean()
                eff = 100.0 * sw_tr[sel].sum() / len(tr_idx)
                msg.append(f'{name} {raw:.1f}%→{eff:.1f}%')
        print(f'phase-weight : {pw_spec}  (mass: ' + '  '.join(msg) + ')')

    print(f'L-BFGS  l2={args.l2}  max_iter={args.max_iter}'
          f'{"  LOGISTIC" if logistic else ""}'
          f'{"  (anchored)" if use_anchor else "  (pure)"}'
          f'{"  [lowmem]" if lm else (f"  [minibatch {mb:,}]" if mb else "")}')
    if (lm or mb > 0) and use_anchor:
        raise SystemExit('--lowmem/--minibatch are pure-L2 only (anchors/freq-reg unsupported)')
    t0 = time.time()
    if lm:
        w_float, train_loss, n_iter = train_lbfgs_lowmem(
            Xpat_tr, ex_tr, wmg[tr_idx], weg[tr_idx], y_tr, args.l2, args.max_iter,
            logistic, PAT_N, EVAL_NUM_EXTRAS, sw=sw_tr)
    elif mb > 0:
        w_float, train_loss, n_iter = train_lbfgs_chunked(
            build, tr_idx, y_black, args.l2, args.max_iter, logistic, n_cols, mb,
            sw_all=sw_all)
    else:
        w_float, train_loss, n_iter = train_lbfgs(X_tr, y_tr, args.l2, args.max_iter,
                                                  prior=prior if use_anchor else None,
                                                  anchor_l2=anchor, logistic=logistic,
                                                  sw=sw_tr)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  ({time.time() - t0:.2f}s)')

    if lm:
        val_pred = lowmem_z(Xpat_val, ex_val.astype(np.float32, copy=False),
                            wmg[val_idx], weg[val_idx], w_float, PAT_N, EVAL_NUM_EXTRAS)
    else:
        val_pred = X_val @ w_float
    val_mse = float(np.mean((val_pred - y_val) ** 2))
    val_sign_acc = float(np.mean(np.sign(val_pred) == y_val))
    print(f'val   : mse={val_mse:.6f}  sign_acc={val_sign_acc:.4f}')
    # Per-phase val_mse (UNWEIGHTED) : the densification microscope — shows
    # whether --phase-weight actually shrank the endgame fit error, and at what
    # cost to the opening. Always printed (cheap, useful even at weight 1.0).
    pc_val = pc[val_idx]
    sq = (val_pred - y_val) ** 2
    pv = '  '.join(f'{name}={float(sq[m].mean()):.4f}(n{int(m.sum())})'
                   for name, lo, hi in PHASE_BOUNDS
                   if (m := (pc_val >= lo) & (pc_val <= hi)).any())
    print(f'val/phase mse : {pv}')

    def quant(block):
        q = np.round(block * args.scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    E = EVAL_NUM_EXTRAS
    pat_mg_d = w_float[0:PAT_N]
    pat_eg_d = w_float[PAT_N:2 * PAT_N]
    ext_mg = quant(w_float[2 * PAT_N:2 * PAT_N + E])
    ext_eg = quant(w_float[2 * PAT_N + E:2 * PAT_N + 2 * E])
    # (1) un-prune to the TRAINING-layout block (size TB : 8.5M if --color-fold else 17M).
    if remap is not None:
        canon_mg = np.zeros(TB, dtype=w_float.dtype)
        canon_eg = np.zeros(TB, dtype=w_float.dtype)
        kept = np.flatnonzero(remap > 0)
        canon_mg[kept] = pat_mg_d[remap[kept]]
        canon_eg[kept] = pat_eg_d[remap[kept]]
    else:
        canon_mg, canon_eg = np.asarray(pat_mg_d), np.asarray(pat_eg_d)
    # (2) --color-fold : EXPAND the canonical (8.5M) block to the standard 17M men-only
    # layout with antisymmetry  W_full[u] = sign(u)·w_canon[|signed(u)|]  → standard v3.
    if rf_canon is not None:
        # --rot-fold : full[p*NB+c] = sign[p][c]·w_canon[canon_col[p][c]] (canonical
        # weights live in the 17M index space; canon_mg is the un-pruned 17M block).
        full_mg = (rf_sign.ravel().astype(w_float.dtype) * canon_mg[rf_canon.ravel()])
        full_eg = (rf_sign.ravel().astype(w_float.dtype) * canon_eg[rf_canon.ravel()])
        pat_mg, pat_eg = quant(full_mg), quant(full_eg)
    elif cf_U2C is not None:
        NB = patterns.BUCKETS_PER_PATTERN                 # 531441
        TBfull = NB * patterns.NUM_PATTERNS
        # Canonical bucket 0 (|signed|=0) is the all-empty config — the colour-swap
        # FIXPOINT, whose antisymmetric weight must be 0. Pin it (per pattern).
        canon_mg[np.arange(patterns.NUM_PATTERNS) * CF_BUCKETS] = 0
        canon_eg[np.arange(patterns.NUM_PATTERNS) * CF_BUCKETS] = 0
        full_mg = np.empty(TBfull, dtype=w_float.dtype)
        full_eg = np.empty(TBfull, dtype=w_float.dtype)
        for p in range(patterns.NUM_PATTERNS):
            cb_mg = canon_mg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            cb_eg = canon_eg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            full_mg[p * NB:(p + 1) * NB] = cf_U2S * cb_mg[cf_U2C]
            full_eg[p * NB:(p + 1) * NB] = cf_U2S * cb_eg[cf_U2C]
        pat_mg, pat_eg = quant(full_mg), quant(full_eg)
    else:
        pat_mg, pat_eg = quant(canon_mg), quant(canon_eg)
    print(f'quant : scale={args.scale}  '
          f'pat range=[{int(pat_mg.min())},{int(pat_mg.max())}] '
          f'ext_mg range=[{int(ext_mg.min())},{int(ext_mg.max())}]')

    if args.fm_rank > 0:
        if X_tr is None:
            raise SystemExit('--fm-rank needs the full design matrix; incompatible with '
                             '--lowmem/--minibatch (they never build X_tr). Drop one.')
        # Boosting : fit a pattern-only FM term on the LINEAR residual (in the
        # same piece-units the C++ adds it). idx holds the raw per-pattern
        # buckets; the FM hashes them. Emit v4 (v3 linear + FM tables).
        r_tr = (y_tr - (X_tr @ w_float)).astype(np.float64)
        r_val = (y_val - val_pred).astype(np.float64)
        V = fit_pattern_fm(idx[tr_idx], r_tr, idx[val_idx], r_val,
                           args.fm_hash, args.fm_rank, args.l2_fm,
                           args.max_iter, seed=2027)
        write_weights_v4(Path(args.out), pat_mg, pat_eg, ext_mg, ext_eg,
                         args.scale, V, args.fm_hash, args.fm_rank,
                         king=getattr(args, 'king_patterns', False))
        nfm = patterns.NUM_PATTERNS * args.fm_hash * args.fm_rank
        print(f'wrote {args.out}  (v4, linear {2*(TB+E)} + FM {nfm} floats)')
        return 0

    write_weights_v3(Path(args.out), pat_mg, pat_eg, ext_mg, ext_eg, args.scale,
                     king=getattr(args, 'king_patterns', False))
    total = 2 * (len(pat_mg) + E)   # len(pat_mg)=17M even under --color-fold (expanded)
    print(f'wrote {args.out}  (v3, {total} weights, {20 + 4 * total} bytes)')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True, help='JNNW master dataset path')
    ap.add_argument('--out',  required=True, help='output PJTW weights path')
    ap.add_argument('--max-records', type=int, default=None,
                    help='cap on records loaded (for smoke runs)')
    ap.add_argument('--l2',   type=float, default=1e-5)
    ap.add_argument('--max-iter', type=int, default=200)
    ap.add_argument('--minibatch', type=int, default=0,
                    help='rows per chunk for memory-bounded L-BFGS (0=full-batch). '
                         'Same optimum, streamed assembly — lets the fit scale to '
                         '10-40M rows on a fixed RAM budget. Pure L2 only.')
    ap.add_argument('--lowmem', action='store_true',
                    help='memory-efficient FULL-BATCH L-BFGS : keep only the compact '
                         'phased pattern sparse + raw extras (dense n×2E never built). '
                         'Same optimum, full-batch SPEED, ~20M rows on 32GB. Preferred '
                         'over --minibatch for <=~20M. Pure L2 only.')
    ap.add_argument('--phase-weight', default='',
                    help='densification knob : over/under-weight rows of a game '
                         'phase in the DATA loss, e.g. "endgame=3,deep-eg=4" (phases: '
                         'opening/midgame/late-mid/endgame/deep-eg, by piece count, '
                         'same bounds as game_autopsy). Unlisted=1.0. Normalised so the '
                         'mean train weight stays 1 (L2 comparable). Works with full / '
                         '--lowmem / --minibatch; the per-phase val_mse print shows the '
                         'effect. Linear-class fix for the endgame bleed (Scan proves a '
                         'linear eval CAN play endgames — feed it more endgame weight, '
                         'no non-linearity). cf jobs 0249/0250/0251/0252.')
    ap.add_argument('--scale', type=int, default=1000)
    ap.add_argument('--val-frac', type=float, default=0.1)
    ap.add_argument('--target', choices=['wdl', 'score', 'prob'], default='wdl',
                    help='training target : "wdl" (ternary {-1,0,1}) or '
                         '"score" (centipawn clipped to ±2000 / 100 → piece units)')
    ap.add_argument('--score-clip', type=float, default=2000.0,
                    help='clip score to ±N cp before scaling (default 2000)')
    ap.add_argument('--score-drop', type=float, default=0.0,
                    help='DROP rows with |raw score| > N cp (extreme won/lost '
                         'verdicts that dominate the LS loss). 0 = keep all. '
                         'Try 4900 (cf 0169: val_mse 38→1.8, play 0.42→0.83).')
    ap.add_argument('--quiet-flags-file', default=None,
                    help='(scan-eval) path to a "QIET" sidecar from '
                         '--dump-quiet-flags ; restrict the fit to quiet '
                         '(non-capture) positions.')
    ap.add_argument('--loss', choices=['ls', 'logistic'], default='ls',
                    help="(scan-eval) 'ls' = least-squares on the target ; "
                         "'logistic' = Scan's objective : logistic regression on "
                         "game OUTCOMES (WDL), eval score = logit. Disables the "
                         "material anchor (logit scale != piece-units).")
    ap.add_argument('--wdl-scale', type=float, default=1.0,
                    help='(--target wdl) map WDL {-1,0,1} to ±N piece-units so '
                         'the target shares the score eval scale (self-play '
                         'loop : keeps the anti-forgetting anchor consistent).')
    ap.add_argument('--fm-rank', type=int, default=0,
                    help='(scan-eval) if >0, fit a pattern-only Factorization-'
                         'Machine term on the linear residual and emit PJTW v4 '
                         '(linear + rank-k pairwise pattern interactions).')
    ap.add_argument('--fm-hash', type=int, default=8192,
                    help='(--fm-rank) hash slots per pattern for the FM tables.')
    ap.add_argument('--l2-fm', type=float, default=1e-3,
                    help='(--fm-rank) L2 on the FM factors.')
    ap.add_argument('--freq-reg', type=float, default=0.0,
                    help='(scan-eval) frequency-weighted L2 on pattern buckets : '
                         'per-column anchor toward 0 = STRENGTH/(visits+1). Rare '
                         '(under-trained) buckets shrunk hard, common ones left '
                         'alone — fights depth-instability without collisions.')
    ap.add_argument('--king-patterns', action='store_true',
                    help='(scan-eval) PIECE-PRESENCE patterns : read men|kings per '
                         'colour so a king-occupied square is VISIBLE to the pattern '
                         '(today men-only -> kings read as empty). 3-state, no bucket '
                         'blow-up; king VALUE stays in the PST extras. A/B vs men-only '
                         'to test if the men-only blindness is the ~0.46 wall. NB: '
                         'changes pattern semantics -> needs the matching C++ extract '
                         '(men|kings) to be playable; this flag is for the fit A/B.')
    ap.add_argument('--prune', action='store_true',
                    help='(scan-eval) train over a COLLISION-FREE dense remap of '
                         'the pattern table : only buckets occurring in the train '
                         'split get a column (slot 1..K), all others share slot 0. '
                         'Cuts the design from 2×17M to 2×(K+1) columns (~22× '
                         'fewer params → far cheaper/faster L-BFGS, less RAM) and '
                         'SCATTERS the result back into a standard 17M-layout '
                         '.pjtw, so the C++ eval is unchanged and bit-compatible. '
                         'Lossless: dropped buckets are unseen→0, exactly as a '
                         'full-table fit leaves them. NOT the lossy hashing of '
                         '0190 (zero collisions). Incompatible with anchors/'
                         'freq-reg/fm (those index the full table).')
    ap.add_argument('--prune-min-visits', type=int, default=1,
                    help='with --prune : keep a bucket only if it occurs >= this '
                         'many times in the train split (2 drops singleton noise).')
    ap.add_argument('--refl-fold', action='store_true',
                    help='(scan-eval) add LEFT-RIGHT REFLECTION (exact board symmetry, '
                         'within-row reversal) to the fold group. Our diag/anti/horiz '
                         'are LR-orphans (geometry not LR-closed) so it only folds the '
                         'vband/sq pairs here. Composes with --trans-fold.')
    ap.add_argument('--full-fold', action='store_true',
                    help='(scan-eval) the FULL symmetry stack : colour + rot180 + '
                         'translation + reflection. Folds 17M -> ~1.0M weights '
                         '(~Scan scale). Exact symmetries (rot180∘cs, LR) preserved; '
                         'translation is approximate. cf docs/SYMMETRY_SHARING.md.')
    ap.add_argument('--trans-fold', action='store_true',
                    help='(scan-eval) Phase-3 : --rot-fold PLUS translation tying (the '
                         '7 translate-classes share tables). Folds 17M->~1.2M weights '
                         '(~Scan scale). WARNING: translation is APPROXIMATE (absolute '
                         'board position matters in draughts) — test by Elo, do not '
                         'assume correct. Expanded to standard 17M v3 .pjtw.')
    ap.add_argument('--rot-fold', action='store_true',
                    help='(scan-eval) Phase-2 symmetry sharing : the group {id, '
                         'colour-swap, rot180, rot180∘colour-swap}. The board exact '
                         'symmetry is rot180∘colour-swap (eval negates); pairs '
                         'v_top_k<->v_bot_(3-k), diag/anti/sq pairs + diag_3 self '
                         '(horiz orphans fall back to colour-fold). Ties ~3.5x more '
                         'weights than men-only (17M->4.9M). Expanded to a standard '
                         '17M v3 .pjtw (C++ unchanged). Supersedes --color-fold; '
                         'composes with --prune. cf docs/SYMMETRY_SHARING.md.')
    ap.add_argument('--color-fold', action='store_true',
                    help='(scan-eval) COLOUR-ANTISYMMETRY weight-sharing (Scan brick, '
                         'cf docs/SYMMETRY_SHARING.md). Encode each pattern with a '
                         'SIGNED balanced-ternary index (black=+1, white=-1, empty=0) '
                         'and train one antisymmetric weight per |index| : a config '
                         'and its colour-swap SHARE a weight (W[swap]=-W). Halves the '
                         'pattern table (531441->265721/pattern, 17M->8.5M) and gives '
                         '2x data per weight. Output is EXPANDED back to a standard '
                         '17M v3 .pjtw (W_full[u]=sign(u)*w_canon[|signed(u)|]), so '
                         'the C++ eval is unchanged. Composes with --prune.')
    ap.add_argument('--skeleton-data', default=None,
                    help='optional path to a sibling JNNW whose score field '
                         'contains the handcrafted skeleton eval per record. '
                         'When set with --target score, the actual training '
                         'target becomes (score - skeleton_score) — the pattern '
                         'learns the RESIDUAL on top of the skeleton (Scan-style '
                         'hybrid). Records must align 1-to-1 with --data.')
    ap.add_argument('--phase-split', action='store_true',
                    help='train 2 weight banks (mg/eg) interpolated by piece '
                         'count → PJTW v2. Rend le pattern game-stage aware '
                         '(comme Scan), lève le plafond mono-phase.')
    ap.add_argument('--phase-lo', type=float, default=0.0,
                    help='phase ramp low (pieces): wmg=0 at/below this. Default 0 '
                         '(=legacy pc/40). MUST match the C++ build -DJASS_PHASE_LO.')
    ap.add_argument('--phase-hi', type=float, default=40.0,
                    help='phase ramp high (pieces): wmg=1 at/above this. Default 40. '
                         'Sharper (e.g. 10/24) specialises the endgame bank (0310).')
    ap.add_argument('--king-features', action='store_true',
                    help='FIT-CHECK only : append 100 king-PST one-hot features '
                         '(the men-only patterns are blind to kings). The '
                         'output .pjtw is then NON-standard (not playable) — '
                         'use only to read val_mse and test if king info helps.')
    ap.add_argument('--features-file', default=None,
                    help='FIT-CHECK only : a "FEAT" file from `jass '
                         '--dump-features` (mobility / balance the static '
                         'men-patterns cannot see). Appended as standardised '
                         'extra columns to test if DYNAMIC info explains the '
                         'residual. Output .pjtw non-playable.')
    ap.add_argument('--scan-eval', action='store_true',
                    help='Train the FULL Scan-style structured eval → PJTW v3 '
                         '(PLAYABLE). Phase-split men patterns + dense extras '
                         '(material + king PST + mobility + balance, all '
                         'MG/EG). Requires --eval-features-file (the raw '
                         'extras from `jass --dump-eval-features`). Implies '
                         'phase-split; target is the score as-is (standalone '
                         'eval, no skeleton residual).')
    ap.add_argument('--eval-features-file', default=None,
                    help='RAW "FEAT" file from `jass --dump-eval-features` '
                         f'({EVAL_NUM_EXTRAS} Scan-style extras). Used with '
                         '--scan-eval to build the playable v3 eval. Values '
                         'are kept RAW (not standardised) so the weights apply '
                         'to the exact features the C++ eval computes.')
    ap.add_argument('--anchor-weights', default=None,
                    help='TD-leaf fine-tuning : a prior v3 PJTW (the Scan-'
                         'distilled eval) toward which the fit is L2-'
                         'regularised. Anti-forgetting anchor. Omit for a '
                         'PURE (unanchored) fine-tune.')
    ap.add_argument('--anchor-l2', type=float, default=0.0,
                    help='Strength of the --anchor-weights pull (0 = off).')
    ap.add_argument('--material-anchor', type=float, default=0.0,
                    help='STANDALONE FIX (cf 0151): per-column L2 pinning the '
                         'material extras (men count, king PST) to sane '
                         'piece-units so the men-count/patterns collinearity '
                         'cannot scramble material. 0 = off. Try ~0.5-2.0.')
    ap.add_argument('--man-pu',  type=float, default=1.0,
                    help='Target piece-units for a man (material anchor).')
    ap.add_argument('--king-pu', type=float, default=3.0,
                    help='Target piece-units for a king (material anchor).')
    args = ap.parse_args()

    if args.scan_eval:
        return train_scan_eval(args)

    # --phase-weight is a scan-eval (structured eval) feature : fail loudly
    # rather than silently ignore it on the legacy pattern-only path.
    if getattr(args, 'phase_weight', ''):
        raise SystemExit('--phase-weight requires --scan-eval (structured eval path)')

    print(f'loading JNNW {args.data}')
    t0 = time.time()
    ds = master_loader.load(args.data, max_records=args.max_records)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    print('extracting pattern indices (men only)')
    t0 = time.time()
    idx = patterns.extract_indices(ds.black_men, ds.white_men)
    cols = patterns.flat_feature_columns(idx)
    print(f'  shape {cols.shape} buckets={patterns.TOTAL_BUCKETS}  '
          f'({time.time() - t0:.2f}s)')

    # Re-project the chosen target to black-POV.
    # JNNW stm: 0 = white-to-move, 1 = black-to-move (cf src/main.cpp:222).
    # WDL and score are both STM-POV in the file.
    # black-POV value = stm-POV if stm==1 else -(stm-POV).
    if args.target == 'wdl':
        target_stm = ds.wdl.astype(np.float64)
        # Diagnostic : WDL distribution (helps catch sparse/all-zero datasets).
        n_pos = int((ds.wdl > 0).sum()); n_neg = int((ds.wdl < 0).sum())
        n_zero = int((ds.wdl == 0).sum())
        print(f'target=wdl  pos={n_pos} neg={n_neg} zero={n_zero}'
              f'  ({n_zero/ds.n_records*100:.1f}% draws)')
    else:  # score
        clipped = np.clip(ds.score.astype(np.float64), -args.score_clip, args.score_clip)
        target_stm = clipped / 100.0  # centipawn → piece units
        print(f'target=score  range=[{int(ds.score.min())},{int(ds.score.max())}]'
              f'  clipped±{int(args.score_clip)}cp / 100 → piece units'
              f'  std={target_stm.std():.3f}')

        if args.skeleton_data is not None:
            print(f'loading skeleton {args.skeleton_data}')
            sk_ds = master_loader.load(args.skeleton_data, max_records=args.max_records)
            if sk_ds.n_records != ds.n_records:
                raise SystemExit(f'skeleton record count {sk_ds.n_records} != '
                                 f'data {ds.n_records}')
            sk_clipped = np.clip(sk_ds.score.astype(np.float64),
                                 -args.score_clip, args.score_clip)
            skeleton_stm = sk_clipped / 100.0
            residual = target_stm - skeleton_stm
            print(f'skeleton std={skeleton_stm.std():.3f}  '
                  f'residual std={residual.std():.3f}  '
                  f'(corr score↔skel = {np.corrcoef(target_stm, skeleton_stm)[0,1]:.3f})')
            target_stm = residual
    y_black = np.where(ds.stm == 1, target_stm, -target_stm)
    wdl_black = y_black  # keep variable name for downstream code

    # Train/val split.
    n = ds.n_records
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    out_version = WEIGHTS_VERSION
    if args.phase_split:
        pc  = np.minimum(piece_count(ds), 40).astype(np.float64)
        wmg = phase_wmg(pc, args.phase_lo, args.phase_hi)
        weg = 1.0 - wmg
        print(f'phase-split : piece-count mean={pc.mean():.1f}  '
              f'wmg mean={wmg.mean():.3f} (1=tout midgame, 0=tout endgame)')
        X_tr  = build_sparse_X_phased(cols[tr_idx],  wmg[tr_idx],  weg[tr_idx],  patterns.TOTAL_BUCKETS)
        X_val = build_sparse_X_phased(cols[val_idx], wmg[val_idx], weg[val_idx], patterns.TOTAL_BUCKETS)
        out_version = 2
    else:
        X_tr  = build_sparse_X(cols[tr_idx],  patterns.TOTAL_BUCKETS)
        X_val = build_sparse_X(cols[val_idx], patterns.TOTAL_BUCKETS)
    y_tr, y_val = wdl_black[tr_idx], wdl_black[val_idx]

    if args.king_features:
        kb = king_onehot_block(ds.black_kings, ds.white_kings)
        X_tr  = sp.hstack([X_tr,  kb[tr_idx]],  format='csr')
        X_val = sp.hstack([X_val, kb[val_idx]], format='csr')
        print(f'king-features : +{kb.shape[1]} king-PST features '
              f'(men-patterns + kings ; fit-check, non-jouable)')

    if args.features_file:
        ef = sp.csr_matrix(load_feature_file(args.features_file, ds.n_records))
        X_tr  = sp.hstack([X_tr,  ef[tr_idx]],  format='csr')
        X_val = sp.hstack([X_val, ef[val_idx]], format='csr')
        print(f'features-file : +{ef.shape[1]} dynamic/global features '
              f'(mobility, balance ; fit-check, non-jouable)')

    print(f'L-BFGS  l2={args.l2}  max_iter={args.max_iter}')
    t0 = time.time()
    w_float, train_loss, n_iter = train_lbfgs(X_tr, y_tr, args.l2, args.max_iter)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  '
          f'({time.time() - t0:.2f}s)')

    val_pred = X_val @ w_float
    val_mse = float(np.mean((val_pred - y_val) ** 2))
    val_sign_acc = float(np.mean(np.sign(val_pred) == y_val))
    print(f'val   : mse={val_mse:.6f}  sign_acc={val_sign_acc:.4f}')

    w_scaled = np.round(w_float * args.scale).astype(np.int64)
    w_scaled = np.clip(w_scaled, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)
    print(f'quant : scale={args.scale}  '
          f'range=[{int(w_scaled.min())},{int(w_scaled.max())}]  '
          f'nnz={int((w_scaled != 0).sum())}')

    write_weights(Path(args.out), w_scaled, args.scale, version=out_version)
    print(f'wrote {args.out}  (v{out_version}, {len(w_scaled)} weights, '
          f'{16 + 4 * len(w_scaled)} bytes)')


if __name__ == '__main__':
    main()
