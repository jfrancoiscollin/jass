#!/usr/bin/env python3
# rank_finetune.py — PISTE (a) comparison training / Bonanza-MMTO.
# Fine-tune une eval pattern (v3 pjtw) sur une LOSS DE RANG sur fratries, ancrée au champion (WDL reste l'ancre via
# anchor·‖w−w0‖²). Corpus = paires JNNW consécutives (2k=preferre, 2k+1=domine ; cf --gen-siblings / --played-moves).
#
# POV (résolu) : le parent préfère l'enfant de PLUS BASSE valeur pour l'adversaire = plus basse eval-STM-enfant.
#   e_stm(enfant) = sign·(X·w), sign=+1 si enfant Noir-au-trait sinon −1 (les 2 enfants d'une paire partagent le STM).
#   "preferre" doit avoir e_stm PLUS BAS => d = sign·((X_worse−X_better)·w) > 0. L = −log σ(s·d).
#
# 3 GARDE-FOUS auto (abort si faux) : (1) POV gate — X·w0 corrèle à jass --eval-position (pipeline correct) ;
#   (2) grad-check différences-finies ; (3) pairwise-accuracy AVANT/APRÈS (doit MONTER, sinon signe faux).
import argparse, struct, sys, subprocess, math
from pathlib import Path
import numpy as np, scipy.sparse as sp
from scipy.optimize import fmin_l_bfgs_b

def _load_champion(path):
    """Loader v3 ROBUSTE : accepte les 2 magics (PJTW=train, PJSW=scan-eval), masque les bits marqueurs
    de version (SELFDESC 0x200 / KING 0x100), lit n_ext + king DU HEADER. Layout = header(20o) + int32
    [pat_mg|pat_eg|ext_mg|ext_eg]. Retourne (w_float, scale, n_pat, n_ext, king)."""
    import struct as _st
    raw = Path(path).read_bytes()
    magic, ver, scale, n_pat, n_ext = _st.unpack_from('<IIIII', raw, 0)
    if magic not in (0x57544A50, 0x57534A50):
        sys.exit(f'{path}: magic inconnu {magic:#x} (attendu PJTW/PJSW)')
    if (ver & 0xFF) != 3:
        sys.exit(f'{path}: version base {ver & 0xFF}!=3 (ver={ver})')
    king = bool(ver & 0x100)
    total = 2 * (n_pat + n_ext)
    arr = np.frombuffer(raw, dtype='<i4', offset=20, count=total).astype(np.float64) / float(scale)
    return arr, int(scale), int(n_pat), int(n_ext), king

def _rec_fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--champion',required=True); ap.add_argument('--pairs',required=True)
    ap.add_argument('--feat',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--tools',required=True)
    ap.add_argument('--lam',type=float,default=0.3); ap.add_argument('--anchor',type=float,default=1e-3)
    ap.add_argument('--min-pairs',type=int,default=1); ap.add_argument('--rank-scale',type=float,default=1.0); ap.add_argument('--max-iter',type=int,default=60)
    ap.add_argument('--full-fold',action='store_true'); ap.add_argument('--color-fold',action='store_true')
    ap.add_argument('--king-patterns',action='store_true'); ap.add_argument('--tempo-stage',action='store_true')
    ap.add_argument('--phase-lo',type=int,default=8); ap.add_argument('--phase-hi',type=int,default=40)
    ap.add_argument('--verify-jass',default=''); ap.add_argument('--verify-n',type=int,default=60)
    # MMTO (--gen-siblings --leaf-mode) : les 2 records d'une paire sont des FEUILLES-PV qui peuvent avoir des STM
    # differents (parites de PV differentes). X·w etant black-POV (fold bitboard-only), la valeur est correcte, mais le
    # SIGNE de la comparaison doit venir du stm du PARENT S (constant par paire), stocke dans le champ score par gen-siblings.
    ap.add_argument('--chunk',type=int,default=0,
                    help='fit STREAMÉ par chunks de PAIRES (0=full-batch RAM ; >0=streamé exact, évite OOM sur gros corpus). Gradient identique au full-batch (somme sur paires découpée).')
    ap.add_argument('--leaf-pov',action='store_true',
                    help='MMTO : derive le signe de la paire du stm parent (champ score), pas du stm du record-feuille')
    a=ap.parse_args()
    sys.path.insert(0,a.tools)
    import patterns, train                                   # noqa
    from train import build_sparse_X_phased, build_extras_phased, write_weights_v3, phase_wmg
    import train_stream as TS
    fold='color' if a.color_fold else ('full' if a.full_fold else 'color')
    folder=TS.Folder(fold)

    # ---- 1. champion weights (aligné [pat_mg|pat_eg|ext_mg|ext_eg]) ----
    w0,scale_c,n_pat,n_ext,king=_load_champion(a.champion)   # king/n_ext LUS DU HEADER (auto)
    print(f'champion : n_pat={n_pat:,} n_ext={n_ext} scale={scale_c} king={king} ; fold={fold} tempo={a.tempo_stage}',flush=True)

    # ---- 2. lire paires + features, construire X (mêmes conventions que train_stream) ----
    raw=Path(a.pairs).read_bytes(); assert raw[:4]==b'JNNW'; nrec=struct.unpack('<I',raw[4:8])[0]; body=raw[8:]
    REC=38; N=nrec
    wm=np.empty(N,np.uint64);wk=np.empty(N,np.uint64);bm=np.empty(N,np.uint64);bk=np.empty(N,np.uint64);stm=np.empty(N,np.int64)
    pov_S=np.empty(N,np.int64)                               # MMTO : stm parent (champ score) — utilise si --leaf-pov
    for i in range(N):
        o=i*REC; a4=struct.unpack('<QQQQ',body[o:o+32]); wm[i],wk[i],bm[i],bk[i]=a4; stm[i]=body[o+32]
        pov_S[i]=struct.unpack('<i',body[o+33:o+37])[0]
    mmf,ncol_feat=TS.open_feat(a.feat,N)                     # saute le header FEAT (12o) + valide cnt==N
    assert ncol_feat==n_ext, f'extras {ncol_feat}!={n_ext} (champion) => mauvaise config eval-features'

    # ================= FIT STREAMÉ (--chunk) : gradient EXACT chunké par paires, sans OOM =================
    if a.chunk and a.chunk>0:
        ncol=w0.size; P=N//2; s=a.rank_scale; CH=int(a.chunk)
        def _foldX(r0,r1):
            wm_c=wm[r0:r1];wk_c=wk[r0:r1];bm_c=bm[r0:r1];bk_c=bk[r0:r1]
            pb_c=(bm_c|bk_c) if king else bm_c; pw_c=(wm_c|wk_c) if king else wm_c
            cols_c,signs_c=folder.cols_signs(pb_c,pw_c)
            if a.tempo_stage: wmg_c=TS._tempo_wmg_bb(wm_c,bm_c)
            else:
                pc=np.minimum(TS._piece_count_bb(wm_c,wk_c,bm_c,bk_c),40).astype(np.float64); wmg_c=phase_wmg(pc,a.phase_lo,a.phase_hi)
            weg_c=1.0-wmg_c
            Xp=build_sparse_X_phased(cols_c,wmg_c,weg_c,n_pat,signs_c)
            Xe=build_extras_phased(np.asarray(mmf[r0:r1],dtype=np.float64),wmg_c,weg_c)
            return sp.hstack([Xp,Xe],format='csr').astype(np.float64)
        def _Dchunk(lo,hi):
            m2=2*(hi-lo); Xc=_foldX(2*lo,2*hi); Xb=Xc[0:m2:2]; Xw=Xc[1:m2:2]
            if a.leaf_pov: sg=np.where(pov_S[2*lo:2*hi:2]==0,1.0,-1.0)
            else:          sg=np.where(stm[2*lo:2*hi:2]==1,1.0,-1.0)
            return (Xw-Xb).multiply(sg[:,None]).tocsr()
        # POV gate (échantillon de records, X construit à la volée)
        if a.verify_jass:
            idx=np.linspace(0,N-1,min(a.verify_n,N)).astype(int)
            eb=np.array([float(_foldX(int(i),int(i)+1).dot(w0)[0]) for i in idx])
            cpp=[]
            for i in idx:
                fen=_rec_fen(int(wm[i]),int(wk[i]),int(bm[i]),int(bk[i]),int(stm[i]))
                try:
                    out=subprocess.run([a.verify_jass,'--eval-position',a.champion,fen],capture_output=True,text=True,timeout=20).stdout
                    cpp.append(float(out.strip().split()[0]))
                except Exception: cpp.append(float('nan'))
            cpp=np.array(cpp); cbl=np.where(stm[idx]==1,cpp,-cpp); m=~np.isnan(cbl)
            def spear(x,y):
                xr=np.argsort(np.argsort(x)); yr=np.argsort(np.argsort(y)); return np.corrcoef(xr,yr)[0,1]
            rho=spear(eb[m],cbl[m]); print(f'[POV gate] Spearman(X·w0 , jass-eval) = {rho:.4f} (n={int(m.sum())}) [streamé]',flush=True)
            if not (rho>0.95): sys.exit(f'ABORT POV gate rho={rho:.3f}<0.95')
        if a.leaf_pov: print(f'[leaf-pov] signe stm parent ; S=White frac={float((pov_S[0:N:2]==0).mean()):.3f}',flush=True)
        colcnt=np.zeros(ncol,dtype=np.int64)                 # pass 1 : nb paires/colonne (streamé)
        for lo in range(0,P,CH):
            Dc=_Dchunk(lo,min(lo+CH,P)); colcnt+=np.bincount(Dc.indices,minlength=ncol)
        used=np.flatnonzero(colcnt>=a.min_pairs); w0s=w0[used].copy()
        print(f'buckets : {int(np.count_nonzero(colcnt))} visités ; {used.size} gardés (>= {a.min_pairs} paires) [STREAMÉ chunk={CH}]',flush=True)
        def lgp(ws):                                         # loss+grad EXACT (somme chunkée), sur colonnes used
            wf=np.zeros(ncol); wf[used]=ws; nll=0.0; gf=np.zeros(ncol)
            for lo in range(0,P,CH):
                Dc=_Dchunk(lo,min(lo+CH,P)); d=np.asarray(Dc.dot(wf)).ravel()
                z=s*d; sig=0.5*(np.tanh(0.5*z)+1.0); nll+=float(np.sum(-np.log(np.clip(sig,1e-12,1.0))))
                gf+=np.asarray(Dc.T.dot((sig-1.0)*s)).ravel()
            return a.lam*(nll/P)+0.5*a.anchor*float(np.dot(ws-w0s,ws-w0s)), a.lam*(gf[used]/P)+a.anchor*(ws-w0s)
        def paccp(ws):
            wf=np.zeros(ncol); wf[used]=ws; pos=0; tot=0
            for lo in range(0,P,CH):
                Dc=_Dchunk(lo,min(lo+CH,P)); d=np.asarray(Dc.dot(wf)).ravel(); pos+=int((d>0).sum()); tot+=d.size
            return pos/tot if tot else 0.0
        acc0=paccp(w0s); print(f'pairwise-acc champion (avant fit) = {acc0:.4f} ; cols visitées={used.size}',flush=True)
        rng=np.random.default_rng(0); test=rng.choice(used.size,size=min(5,used.size),replace=False)
        L0,g=lgp(w0s); eps=1e-4; ok=True
        for t in test:
            wp=w0s.copy(); wp[t]+=eps; wmn=w0s.copy(); wmn[t]-=eps
            num=(lgp(wp)[0]-lgp(wmn)[0])/(2*eps)
            if abs(num-g[t])>1e-3*(1+abs(g[t])): ok=False; print(f'  grad-check FAIL col{t}: num={num:.4e} ana={g[t]:.4e}')
        print(f'[grad-check] {"OK" if ok else "FAIL"} [streamé]',flush=True)
        if not ok: sys.exit('ABORT grad-check')
        ws,fval,info=fmin_l_bfgs_b(lambda w:lgp(w),w0s,maxiter=a.max_iter,pgtol=1e-6)
        acc1=paccp(ws)
        print(f'fit : loss {L0:.5f}->{fval:.5f} ; pairwise-acc {acc0:.4f}->{acc1:.4f} (delta {acc1-acc0:+.4f})',flush=True)
        if acc1 < acc0 + 1e-3: sys.exit(f'ABORT pairwise-acc n a PAS monté ({acc0:.4f}->{acc1:.4f})')
        w=w0.copy(); w[used]=ws
        wint=np.clip((w*scale_c).round(),-(2**31),2**31-1).astype('<i4')
        with open(a.out,'wb') as f: f.write(Path(a.champion).read_bytes()[:20]); f.write(wint.tobytes())
        print(f'écrit {a.out} (header copié du champion, scale={scale_c}, {used.size} buckets ajustés) [streamé]',flush=True)
        return

    feat=np.asarray(mmf,dtype=np.float64)                    # (N, k)
    pb=(bm|bk) if king else bm; pw=(wm|wk) if king else wm
    cols,signs=folder.cols_signs(pb,pw)
    if a.tempo_stage: wmg=TS._tempo_wmg_bb(wm,bm)
    else:
        pc=np.minimum(TS._piece_count_bb(wm,wk,bm,bk),40).astype(np.float64); wmg=phase_wmg(pc,a.phase_lo,a.phase_hi)
    weg=1.0-wmg
    Xpat=build_sparse_X_phased(cols,wmg,weg,n_pat,signs)
    Xext=build_extras_phased(feat,wmg,weg)
    X=sp.hstack([Xpat,Xext],format='csr').astype(np.float64)   # (N, 2*n_pat+2*n_ext) == len(w0)
    assert X.shape[1]==w0.size, f'X cols {X.shape[1]} != w0 {w0.size}'
    print(f'design : X {X.shape} ; paires={N//2}',flush=True)

    evb0=X.dot(w0)                                            # eval black-POV (logit) sous champion

    # ---- GARDE-FOU 1 : POV gate (X·w0 vs jass --eval-position) ----
    if a.verify_jass:
        idx=np.linspace(0,N-1,min(a.verify_n,N)).astype(int)
        cpp=[]
        for i in idx:
            fen=_rec_fen(int(wm[i]),int(wk[i]),int(bm[i]),int(bk[i]),int(stm[i]))
            try:
                out=subprocess.run([a.verify_jass,'--eval-position',a.champion,fen],capture_output=True,text=True,timeout=20).stdout
                cpp.append(float(out.strip().split()[0]))
            except Exception: cpp.append(float('nan'))
        cpp=np.array(cpp); cbl=np.where(stm[idx]==1,cpp,-cpp)   # C++ en black-POV
        m=~np.isnan(cbl)
        def spear(x,y):
            xr=np.argsort(np.argsort(x)); yr=np.argsort(np.argsort(y))
            return np.corrcoef(xr,yr)[0,1]
        rho=spear(evb0[idx][m],cbl[m])
        print(f'[POV gate] Spearman(X·w0 , jass-eval black-POV) = {rho:.4f} (n={m.sum()})',flush=True)
        if not (rho>0.95): sys.exit(f'ABORT POV gate rho={rho:.3f}<0.95 => X·w0 ne reproduit PAS l eval C++ (config fold/king/extras fausse)')

    # ---- paires : d = sign·((X_worse − X_better)·w) ; sign=+1 si enfant Noir (stm==1) ----
    P=N//2
    Xb=X[0:N:2]; Xw=X[1:N:2]                                  # better (2k), worse (2k+1)
    if a.leaf_pov:
        # MMTO : signe depuis le stm PARENT S (champ score) ; +1 si S==White(0) — équivalent exact du static
        # (static : stm_record=stm_enfant=opposé de S ; where(stm_enfant==Black) <=> where(S==White)).
        sgn=np.where(pov_S[0:N:2]==0,1.0,-1.0)
        print(f'[leaf-pov] signe dérivé du stm parent (champ score) ; S=White frac={float((pov_S[0:N:2]==0).mean()):.3f}',flush=True)
    else:
        sgn=np.where(stm[0:N:2]==1,1.0,-1.0)                  # STM partagé par la paire (enfants immédiats)
    D=(Xw-Xb).multiply(sgn[:,None]).tocsr()                  # (P, ncol) ; d = D·w
    # REGULARISATION anti-overfit : n'ajuster que les buckets vus dans >= min_pairs paires (chaque colonne
    # de D = 1 nnz/paire qui la touche => bincount(indices) = nb de paires par colonne).
    colcnt=np.bincount(D.indices,minlength=D.shape[1])
    used=np.flatnonzero(colcnt>=a.min_pairs)
    print(f'buckets : {np.count_nonzero(colcnt)} visités ; {used.size} gardés (>= {a.min_pairs} paires) ; paires/bucket median={np.median(colcnt[colcnt>0]):.1f}',flush=True)
    Ds=D[:,used].tocsr()                                      # (P, |used|) SPARSE (jamais densifié)
    w0s=w0[used].copy()
    s=a.rank_scale
    def pacc(ws):
        d=np.asarray(Ds.dot(ws)).ravel(); return float((d>0).mean())
    acc0=pacc(w0s)
    print(f'pairwise-acc champion (avant fit) = {acc0:.4f} ; cols visitées={used.size}',flush=True)

    def lg(ws):
        d=np.asarray(Ds.dot(ws)).ravel()                     # (P,)
        z=s*d; sig=0.5*(np.tanh(0.5*z)+1.0)
        loss=a.lam*np.mean(-np.log(np.clip(sig,1e-12,1.0))) + 0.5*a.anchor*np.dot(ws-w0s,ws-w0s)
        g=a.lam*(np.asarray(Ds.T.dot((sig-1.0)*s)).ravel()/P) + a.anchor*(ws-w0s)
        return loss,g

    # ---- GARDE-FOU 2 : grad-check différences-finies ----
    rng=np.random.default_rng(0); test=rng.choice(used.size,size=min(8,used.size),replace=False)
    L0,g=lg(w0s); eps=1e-4; ok=True
    for t in test:
        wp=w0s.copy(); wp[t]+=eps; wm_=w0s.copy(); wm_[t]-=eps
        num=(lg(wp)[0]-lg(wm_)[0])/(2*eps)
        if abs(num-g[t])>1e-3*(1+abs(g[t])): ok=False; print(f'  grad-check FAIL col{t}: num={num:.4e} ana={g[t]:.4e}')
    print(f'[grad-check] {"OK" if ok else "FAIL"}',flush=True)
    if not ok: sys.exit('ABORT grad-check => gradient faux')

    # ---- fit L-BFGS sur colonnes visitées ----
    ws,fval,info=fmin_l_bfgs_b(lambda w:lg(w),w0s,maxiter=a.max_iter,pgtol=1e-6)
    acc1=pacc(ws)
    print(f'fit : loss {L0:.5f}->{fval:.5f} ; pairwise-acc {acc0:.4f}->{acc1:.4f} (delta {acc1-acc0:+.4f})',flush=True)

    # ---- GARDE-FOU 3 : pairwise-acc doit MONTER ----
    if acc1 < acc0 + 1e-3:
        sys.exit(f'ABORT pairwise-acc n a PAS monté ({acc0:.4f}->{acc1:.4f}) => signe de la loss faux ou λ inutile')

    # ---- écrire : COPIER le header EXACT du champion (magic PJSW/PJTW, ver, scale, n_pat, n_ext) + poids fine-tunés ----
    #      => candidat byte-identique au format gen1 (jass le charge à l'identique ; pas de magic PJTW->PJSW mismatch).
    w=w0.copy(); w[used]=ws
    wint=np.clip((w*scale_c).round(),-(2**31),2**31-1).astype('<i4')
    hdr=Path(a.champion).read_bytes()[:20]
    with open(a.out,'wb') as f:
        f.write(hdr); f.write(wint.tobytes())
    print(f'écrit {a.out} (header copié du champion, scale={scale_c}, {used.size} buckets ajustés)',flush=True)

if __name__=='__main__': main()
