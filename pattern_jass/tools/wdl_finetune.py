#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""wdl_finetune.py — PISTE 1 : fine-tune WDL ANCRÉ sur un champion (au lieu d'un refit WDL de zéro).

Motivation (couplage 0646) : refitter une base WDL FRAÎCHE de zéro sur 3M outcomes-Scan donne un
ranker plus FAIBLE que gen2-mmto (pairwise 0.647 vs 0.699) => A/B −50/−61 Elo. Piste 1 = GARDER la
base accumulée du champion et la RAFFINER sur le nouveau WDL, via l'objectif ancré :

    min_w   (1/N) Σ_i CE( σ(z_i/T) , y_i )   +   0.5 · anchor · ‖w − w0‖²        z_i = X_i·w  (black-POV)

exactement la structure de rank_finetune (fit DIRECT dans l'espace champion étendu ; seules les colonnes
VISITÉES par les données bougent ; les non-visitées restent au champion ; header copié du champion), mais
avec la LOSS WDL par POSITION au lieu de la loss de RANG par paires. Réutilise les helpers train/train_stream
et _load_champion (byte-compatibles avec le C++). anchor→0 = fit WDL quasi-libre depuis le champion ;
anchor grand = reste collé au champion. --logit-scale T calibre eval-units→logits (défaut 1 : gen2-mmto EST
une base logistique train_stream, z déjà ~logit ; le diagnostic z-stats l'affiche pour vérifier la non-saturation).

WDL est STM-POV dans le record (byte 37) ; black-POV : y_black = (wdl·[+1 si stm==1 sinon −1] + 1)/2 ∈ {0,0.5,1}.

Garde-fous auto (abort) : (1) POV gate Spearman(X·w0 , jass --eval-position) > 0.95 ; (2) grad-check
différences-finies ; (3) logloss doit DESCENDRE (sinon signe/scale faux).
"""
import argparse, struct, sys, subprocess
from pathlib import Path
import numpy as np, scipy.sparse as sp
from scipy.optimize import fmin_l_bfgs_b


def _load_champion(path):
    """Loader v3 (identique à rank_finetune) : header(20o) + int32[pat_mg|pat_eg|ext_mg|ext_eg]."""
    raw = Path(path).read_bytes()
    magic, ver, scale, n_pat, n_ext = struct.unpack_from('<IIIII', raw, 0)
    if magic not in (0x57544A50, 0x57534A50):
        sys.exit(f'{path}: magic inconnu {magic:#x} (attendu PJTW/PJSW)')
    if (ver & 0xFF) != 3:
        sys.exit(f'{path}: version base {ver & 0xFF}!=3 (ver={ver})')
    king = bool(ver & 0x100)
    total = 2 * (n_pat + n_ext)
    arr = np.frombuffer(raw, dtype='<i4', offset=20, count=total).astype(np.float64) / float(scale)
    return arr, int(scale), int(n_pat), int(n_ext), king


def _rec_fen(wm, wk, bm, bk, stm):
    Wl = []; Bl = []
    for sq in range(1, 51):
        b = 1 << (sq - 1)
        if wm & b: Wl.append(str(sq))
        elif wk & b: Wl.append("K" + str(sq))
        elif bm & b: Bl.append(str(sq))
        elif bk & b: Bl.append("K" + str(sq))
    return f"{'B' if stm == 1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--champion', required=True)
    ap.add_argument('--data', required=True, help='JNNW WDL corpus (wdl STM-POV en byte 37)')
    ap.add_argument('--feat', required=True, help='FEAT (jass --dump-eval-features sur --data)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tools', required=True)
    ap.add_argument('--anchor', type=float, default=1.0, help='force du prior 0.5·anchor·‖w−w0‖²')
    ap.add_argument('--logit-scale', type=float, default=1.0, help='T : p=σ(z/T) (eval-units→logits)')
    ap.add_argument('--min-visits', type=int, default=1)
    ap.add_argument('--max-iter', type=int, default=60)
    ap.add_argument('--chunk', type=int, default=1000000, help='lignes/chunk (streamé exact, sans OOM)')
    ap.add_argument('--full-fold', action='store_true'); ap.add_argument('--color-fold', action='store_true')
    ap.add_argument('--king-patterns', action='store_true'); ap.add_argument('--tempo-stage', action='store_true')
    ap.add_argument('--phase-lo', type=int, default=8); ap.add_argument('--phase-hi', type=int, default=40)
    ap.add_argument('--verify-jass', default=''); ap.add_argument('--verify-n', type=int, default=60)
    a = ap.parse_args()
    sys.path.insert(0, a.tools)
    import patterns, train  # noqa: F401
    from train import build_sparse_X_phased, build_extras_phased, phase_wmg  # noqa: F401
    import train_stream as TS
    fold = 'color' if a.color_fold else ('full' if a.full_fold else 'color')
    folder = TS.Folder(fold)
    T = float(a.logit_scale)

    # ---- 1. champion (aligné [pat_mg|pat_eg|ext_mg|ext_eg]) ----
    w0, scale_c, n_pat, n_ext, king = _load_champion(a.champion)
    print(f'champion : n_pat={n_pat:,} n_ext={n_ext} scale={scale_c} king={king} ; fold={fold} '
          f'tempo={a.tempo_stage} anchor={a.anchor} T={T}', flush=True)

    # ---- 2. lire data (bitboards, stm, wdl) ----
    raw = Path(a.data).read_bytes(); assert raw[:4] == b'JNNW'
    N = struct.unpack('<I', raw[4:8])[0]; body = raw[8:]; REC = 38
    arr = np.frombuffer(body, dtype=np.dtype([
        ('wm', '<u8'), ('wk', '<u8'), ('bm', '<u8'), ('bk', '<u8'),
        ('stm', 'u1'), ('score', '<i4'), ('wdl', 'i1')]), count=N)
    wm = arr['wm'].copy(); wk = arr['wk'].copy(); bm = arr['bm'].copy(); bk = arr['bk'].copy()
    stm = arr['stm'].astype(np.int64); wdl = arr['wdl'].astype(np.float64)
    # black-POV target : wdl_black = wdl si stm==1 (Noir au trait) sinon −wdl ; y = (wdl_black+1)/2
    y_all = ((np.where(stm == 1, wdl, -wdl)) + 1.0) * 0.5
    npos = int((wdl > 0).sum()); nneg = int((wdl < 0).sum()); nz = int((wdl == 0).sum())
    print(f'data : N={N:,} win={npos:,} loss={nneg:,} draw={nz:,} ({100*nz/N:.1f}% nulles)', flush=True)
    mmf, ncol_feat = TS.open_feat(a.feat, N)
    assert ncol_feat == n_ext, f'extras {ncol_feat}!={n_ext} (champion) => mauvaise config eval-features'

    ncol = w0.size; CH = int(a.chunk)

    def _foldX(r0, r1):
        wm_c = wm[r0:r1]; wk_c = wk[r0:r1]; bm_c = bm[r0:r1]; bk_c = bk[r0:r1]
        pb_c = (bm_c | bk_c) if king else bm_c; pw_c = (wm_c | wk_c) if king else wm_c
        cols_c, signs_c = folder.cols_signs(pb_c, pw_c)
        if a.tempo_stage:
            wmg_c = TS._tempo_wmg_bb(wm_c, bm_c)
        else:
            pc = np.minimum(TS._piece_count_bb(wm_c, wk_c, bm_c, bk_c), 40).astype(np.float64)
            wmg_c = phase_wmg(pc, a.phase_lo, a.phase_hi)
        weg_c = 1.0 - wmg_c
        Xp = build_sparse_X_phased(cols_c, wmg_c, weg_c, n_pat, signs_c)
        Xe = build_extras_phased(np.asarray(mmf[r0:r1], dtype=np.float64), wmg_c, weg_c)
        return sp.hstack([Xp, Xe], format='csr').astype(np.float64)

    # ---- POV gate + z-stats (saturation check) ----
    idx = np.linspace(0, N - 1, min(a.verify_n, N)).astype(int)
    z0s = np.array([float(_foldX(int(i), int(i) + 1).dot(w0)[0]) for i in idx])
    print(f'[z-stats champion] z0/T : min={z0s.min()/T:+.2f} max={z0s.max()/T:+.2f} '
          f'std={z0s.std()/T:.2f}  (|z/T|>>6 partout => σ saturée, augmenter --logit-scale)', flush=True)
    if a.verify_jass:
        cpp = []
        for i in idx:
            fen = _rec_fen(int(wm[i]), int(wk[i]), int(bm[i]), int(bk[i]), int(stm[i]))
            try:
                out = subprocess.run([a.verify_jass, '--eval-position', a.champion, fen],
                                     capture_output=True, text=True, timeout=20).stdout
                cpp.append(float(out.strip().split()[0]))
            except Exception:
                cpp.append(float('nan'))
        cpp = np.array(cpp); cbl = np.where(stm[idx] == 1, cpp, -cpp); m = ~np.isnan(cbl)

        def spear(x, y):
            xr = np.argsort(np.argsort(x)); yr = np.argsort(np.argsort(y)); return np.corrcoef(xr, yr)[0, 1]
        rho = spear(z0s[m], cbl[m])
        print(f'[POV gate] Spearman(X·w0 , jass-eval) = {rho:.4f} (n={int(m.sum())})', flush=True)
        if not (rho > 0.95):
            sys.exit(f'ABORT POV gate rho={rho:.3f}<0.95')

    # ---- pass 1 : colonnes visitées (streamé) ----
    colcnt = np.zeros(ncol, dtype=np.int64)
    for lo in range(0, N, CH):
        Xc = _foldX(lo, min(lo + CH, N)); colcnt += np.bincount(Xc.indices, minlength=ncol)
    used = np.flatnonzero(colcnt >= a.min_visits); w0s = w0[used].copy()
    print(f'buckets : {int(np.count_nonzero(colcnt))} visités ; {used.size} gardés (>= {a.min_visits}) '
          f'[STREAMÉ chunk={CH}]', flush=True)

    eps = 1e-12

    def lg(ws):
        wf = np.zeros(ncol); wf[used] = ws; nll = 0.0; gf = np.zeros(ncol)
        for lo in range(0, N, CH):
            hi = min(lo + CH, N); Xc = _foldX(lo, hi)
            z = np.asarray(Xc.dot(wf)).ravel() / T
            p = 0.5 * (np.tanh(0.5 * z) + 1.0)
            yc = y_all[lo:hi]
            nll += float(np.sum(-(yc * np.log(p + eps) + (1.0 - yc) * np.log(1.0 - p + eps))))
            gf += np.asarray(Xc.T.dot((p - yc) / T)).ravel()
        dw = ws - w0s
        return nll / N + 0.5 * a.anchor * float(np.dot(dw, dw)), gf[used] / N + a.anchor * dw

    def logloss(ws):
        return lg(ws)[0] - 0.5 * a.anchor * float(np.dot(ws - w0s, ws - w0s))  # data term only

    L0 = logloss(w0s); print(f'logloss champion (data) = {L0:.6f}', flush=True)
    # grad-check
    rng = np.random.default_rng(0); test = rng.choice(used.size, size=min(5, used.size), replace=False)
    _, g = lg(w0s); okk = True
    for t in test:
        wp = w0s.copy(); wp[t] += 1e-4; wmn = w0s.copy(); wmn[t] -= 1e-4
        num = (lg(wp)[0] - lg(wmn)[0]) / (2e-4)
        if abs(num - g[t]) > 1e-3 * (1 + abs(g[t])):
            okk = False; print(f'  grad-check FAIL col{t}: num={num:.4e} ana={g[t]:.4e}')
    print(f'[grad-check] {"OK" if okk else "FAIL"}', flush=True)
    if not okk:
        sys.exit('ABORT grad-check')

    ws, fval, info = fmin_l_bfgs_b(lambda w: lg(w), w0s, maxiter=a.max_iter, pgtol=1e-6)
    L1 = logloss(ws); moved = float(np.abs(ws - w0s).mean())
    print(f'fit : logloss(data) {L0:.6f}->{L1:.6f} (delta {L1-L0:+.6f}) ; mean|Δw|={moved:.5f} '
          f'sur {used.size} cols', flush=True)
    if L1 > L0 + 1e-6:
        sys.exit(f'ABORT logloss n a PAS descendu ({L0:.6f}->{L1:.6f}) — signe/scale faux ?')

    w = w0.copy(); w[used] = ws
    wint = np.clip((w * scale_c).round(), -(2 ** 31), 2 ** 31 - 1).astype('<i4')
    with open(a.out, 'wb') as f:
        f.write(Path(a.champion).read_bytes()[:20]); f.write(wint.tobytes())
    print(f'écrit {a.out} (header copié du champion, scale={scale_c}, {used.size} buckets ajustés)', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
