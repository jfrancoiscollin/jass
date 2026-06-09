#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
FM fit-check (GATE before building a C++ Factorization-Machine eval).

Question : do PAIRWISE feature interactions reduce held-out error beyond the
linear pattern model ? If yes, an FM (linear + low-rank pairwise term) is worth
building in C++. If the val_mse barely moves, FM won't help either — skip it.

Pure numpy/scipy (no torch). The pattern buckets (32 × 531441) are HASHED to
H slots/pattern to stay tractable for a signal probe; both arms use the SAME
hashed features so the comparison is fair — only the FM term differs.

Model (single-phase, score target ; this is a SIGNAL probe, not a playable eval):
   ŷ = b + Σ_i w_i s_i              (linear : hashed patterns + extras + stage)
       + ½ Σ_f [ (Σ_i s_i V_{i,f})² − Σ_i s_i² V_{i,f}² ]   (FM, rank k)

Reports val_mse(linear) vs val_mse(linear+FM) and the % reduction.
"""
import argparse, sys, time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master_loader
import patterns


def load_extras(path, n):
    raw = Path(path).read_bytes()
    assert raw[:4] == b'FEAT', f'{path}: not FEAT'
    import struct
    cnt, k = struct.unpack_from('<II', raw, 4)
    assert cnt == n, f'feat {cnt} != data {n}'
    a = np.frombuffer(raw, '<f4', cnt * k, 12).reshape(cnt, k).astype(np.float64)
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--eval-features-file', required=True)
    ap.add_argument('--score-clip', type=float, default=5000.0)
    ap.add_argument('--score-drop', type=float, default=4900.0)
    ap.add_argument('--subsample', type=int, default=300000)
    ap.add_argument('--rank', type=int, default=8)
    ap.add_argument('--hash', type=int, default=8192)
    ap.add_argument('--l2', type=float, default=1e-4)
    ap.add_argument('--l2-fm', type=float, default=1e-3)
    ap.add_argument('--max-iter', type=int, default=120)
    ap.add_argument('--seed', type=int, default=2026)
    args = ap.parse_args()

    ds = master_loader.load(args.data)
    n_all = ds.n_records
    idx = patterns.extract_indices(ds.black_men, ds.white_men)   # (n,32) buckets
    extras = load_extras(args.eval_features_file, n_all)          # (n,106)
    stage = (np.minimum(patterns_piece_count(ds), 40) / 40.0)[:, None]  # (n,1)

    # target : score, clipped, /100, black-POV ; drop extremes.
    sc = ds.score.astype(np.float64)
    keep = np.abs(sc) <= args.score_drop
    y_stm = np.clip(sc, -args.score_clip, args.score_clip) / 100.0
    y = np.where(ds.stm == 1, y_stm, -y_stm)

    rng = np.random.default_rng(args.seed)
    kept = np.flatnonzero(keep)
    if len(kept) > args.subsample:
        kept = rng.choice(kept, args.subsample, replace=False)
    perm = rng.permutation(kept)
    n_val = len(perm) // 10
    val, tr = perm[:n_val], perm[n_val:]
    print(f'rows : {len(kept)} kept (of {n_all}) ; train {len(tr)} val {len(val)} ; '
          f'rank={args.rank} hash={args.hash}')

    H, NP, k = args.hash, patterns.NUM_PATTERNS, args.rank
    # hashed pattern slots (global) : pattern p, bucket b -> p*H + (b % H)
    poff = (np.arange(NP) * H).astype(np.int64)
    Pall = ((idx % H) + poff).astype(np.int64)                   # (n,32)
    # standardise extras + stage (conditioning for the probe)
    feats = np.hstack([extras, stage])                            # (n,107)
    mu, sd = feats[tr].mean(0), feats[tr].std(0); sd[sd == 0] = 1
    feats = (feats - mu) / sd
    E = feats.shape[1]
    n_lin = 1 + NP * H + E            # b + w_pat + w_ext
    SLOT = NP * H

    def unpack(theta, fm):
        b = theta[0]
        wpat = theta[1:1 + SLOT]
        wext = theta[1 + SLOT:n_lin]
        if not fm:
            return b, wpat, wext, None, None
        off = n_lin
        Vpat = theta[off:off + SLOT * k].reshape(SLOT, k); off += SLOT * k
        Vext = theta[off:off + E * k].reshape(E, k)
        return b, wpat, wext, Vpat, Vext

    def loss_grad(theta, P, X, yy, fm):
        N = len(yy)
        b, wpat, wext, Vpat, Vext = unpack(theta, fm)
        lin = b + wpat[P].sum(1) + X @ wext
        pred = lin.copy()
        if fm:
            A = X @ Vext                                  # (N,k)
            for f in range(k):
                A[:, f] += Vpat[P, f].sum(1)
            B = (X * X) @ (Vext * Vext)                   # (N,k)
            for f in range(k):
                B[:, f] += (Vpat[P, f] ** 2).sum(1)
            pred = pred + 0.5 * (A * A - B).sum(1)
        r = (pred - yy) / N
        loss = 0.5 * float(np.dot(pred - yy, pred - yy)) / N
        loss += 0.5 * args.l2 * (np.dot(wpat, wpat) + np.dot(wext, wext))
        g = np.zeros_like(theta)
        g[0] = r.sum()
        gwpat = np.zeros(SLOT); np.add.at(gwpat, P.ravel(), np.repeat(r, P.shape[1]))
        g[1:1 + SLOT] = gwpat + args.l2 * wpat
        g[1 + SLOT:n_lin] = X.T @ r + args.l2 * wext
        if fm:
            loss += 0.5 * args.l2_fm * (np.dot(Vpat.ravel(), Vpat.ravel())
                                        + np.dot(Vext.ravel(), Vext.ravel()))
            gVpat = np.zeros((SLOT, k)); gVext = np.zeros((E, k))
            X2 = X * X
            for f in range(k):
                Af = A[:, f]
                gVext[:, f] = X.T @ (r * Af) - Vext[:, f] * (X2.T @ r)
                t1 = (r * Af)[:, None]                      # (N,1)
                np.add.at(gVpat[:, f], P.ravel(), np.repeat(t1[:, 0], P.shape[1]))
                t2 = -(r[:, None] * Vpat[P, f])            # (N,32)
                np.add.at(gVpat[:, f], P.ravel(), t2.ravel())
            off = n_lin
            g[off:off + SLOT * k] = (gVpat + args.l2_fm * Vpat).ravel(); off += SLOT * k
            g[off:off + E * k] = (gVext + args.l2_fm * Vext).ravel()
        return loss, g

    def fit(fm, tag):
        size = n_lin + (SLOT * k + E * k if fm else 0)
        th0 = np.zeros(size)
        if fm:
            th0[n_lin:] = rng.standard_normal(size - n_lin) * 0.01
        t0 = time.time()
        res = minimize(loss_grad, th0, args=(Pall[tr], feats[tr], y[tr], fm),
                       jac=True, method='L-BFGS-B',
                       options={'maxiter': args.max_iter, 'maxcor': 5})
        _, _, _, _, _ = unpack(res.x, fm)
        vl, _ = loss_grad(res.x, Pall[val], feats[val], y[val], fm)
        # val mse only (strip the L2 from the reported number)
        b, wpat, wext, Vpat, Vext = unpack(res.x, fm)
        lin = b + wpat[Pall[val]].sum(1) + feats[val] @ wext
        pred = lin.copy()
        if fm:
            A = feats[val] @ Vext
            for f in range(k):
                A[:, f] += Vpat[Pall[val], f].sum(1)
            Bv = (feats[val] ** 2) @ (Vext * Vext)
            for f in range(k):
                Bv[:, f] += (Vpat[Pall[val], f] ** 2).sum(1)
            pred = pred + 0.5 * (A * A - Bv).sum(1)
        mse = float(np.mean((pred - y[val]) ** 2))
        print(f'  {tag:14s}: val_mse={mse:.4f}  ({time.time()-t0:.1f}s, '
              f'{size} params)')
        return mse

    print('fitting...')
    m_lin = fit(False, 'linear')
    m_fm = fit(True, 'linear+FM')
    red = 100 * (m_lin - m_fm) / m_lin if m_lin else 0
    print('=' * 58)
    print('        FM FIT-CHECK — VERDICT')
    print(f'  linear      val_mse = {m_lin:.4f}')
    print(f'  linear + FM val_mse = {m_fm:.4f}   ({red:+.1f}% vs linear)')
    print('  → réduction nette (>~5-10%) = signal d\'interaction → construire FM C++.')
    print('  → ≈0% = pas d\'interaction exploitable → ne pas construire FM.')
    print('=' * 58)


def patterns_piece_count(ds):
    allbb = (ds.white_men | ds.white_kings | ds.black_men | ds.black_kings)
    bits = np.unpackbits(allbb.view(np.uint8)).reshape(ds.n_records, 64)
    return bits.sum(1)


if __name__ == '__main__':
    main()
