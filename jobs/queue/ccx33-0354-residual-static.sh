#!/usr/bin/env bash
# id: ccx33-0354-residual-static
# description: ÉTAPE 3 — analyse des RÉSIDUS finale. Sur un set fort, on aligne éval-jass et éval-Scan (d2 statique) et on
# (0352 corrigé : cible Scan-d2 STATIQUE, pas d9 cherché) DÉCOMPOSE le gap finale : (a) combien le drawish (÷8/÷2, appliqué en post sur les scores jass) RÉDUIT le résidu
# sur les positions drawish → mesure la part de la non-linéarité ; (b) sur les positions finale NON-drawish, reste-
# t-il un gros résidu → part « qualité des poids ». + dump des pires désaccords finale pour caractériser.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/ccx33-0354-residual-static/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
N=24000
[ -f "$DATA" ] && [ -f "$CORPUS" ] || { echo "ABORT: data manquante"; exit 4; }

preflight_build 1; preflight_train 240000 1; preflight_note "relabel Scan d2 (statique) + analyse résidus" 70; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

echo "=== build + train éval ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/train.log"; exit 9; }

# set fort biaisé finale : positions <=14p
python3 - "$CORPUS" "$ART/test.jnnw" "$N" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]; r=bytearray(); k=0
for i in range(tot):
    rec=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if pc<=14:
        r+=rec; k+=1
        if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r)); print('test (<=14p)',k)
PY
echo "=== relabel Scan d2 (statique) + éval-jass alignée (rewrite-scores SUR le relabel) ==="
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan.jnnw" "$SCAN_BIN" 2 "$NCPU"
"$JASS" --rewrite-scores-with-nnue "$ART/scan.jnnw" "$ART/jass.jnnw" --nnue "$ART/eval.pjtw" >"$ART/rw.log" 2>&1

echo "=== ANALYSE RÉSIDUS (drawish vs poids) ==="
python3 - "$ART/jass.jnnw" "$ART/scan.jnnw" <<'PY'
import sys, struct
import numpy as np
REC = 38
def load(p):
    b = open(p, 'rb').read(); n = struct.unpack('<I', b[4:8])[0]; body = b[8:]
    sc = np.empty(n, np.float64); stm = np.empty(n, np.int8); pc = np.empty(n, np.int32)
    nwm = np.empty(n, np.int32); nwk = np.empty(n, np.int32)
    nbm = np.empty(n, np.int32); nbk = np.empty(n, np.int32); bb = np.empty((n, 4), np.uint64)
    for i in range(n):
        rec = body[i*REC:(i+1)*REC]; wm, wk, bm, bk = struct.unpack('<4Q', rec[0:32]); bb[i] = (wm, wk, bm, bk)
        nwm[i] = bin(wm).count('1'); nwk[i] = bin(wk).count('1'); nbm[i] = bin(bm).count('1'); nbk[i] = bin(bk).count('1')
        pc[i] = nwm[i] + nwk[i] + nbm[i] + nbk[i]; stm[i] = rec[32]; sc[i] = struct.unpack('<i', rec[33:37])[0]
    return sc, stm, pc, nwm, nwk, nbm, nbk, bb
js, jstm, jpc, nwm, nwk, nbm, nbk, jbb = load(sys.argv[1])
ss, sstm, spc, _a, _b, _c, _d, sbb = load(sys.argv[2])
n = min(len(js), len(ss)); assert (jbb[:n] == sbb[:n]).all(), "MISALIGNED"
js, ss, jstm, jpc = js[:n], ss[:n], jstm[:n], jpc[:n]
nwm, nwk, nbm, nbk = nwm[:n], nwk[:n], nbm[:n], nbk[:n]
# aligne l'échelle jass sur Scan (régression) pour comparer des résidus en cp Scan
A = np.vstack([js, np.ones(n)]).T
coef, *_ = np.linalg.lstsq(A, ss, rcond=None); jn = A @ coef
# applique le drawish (black-POV) aux scores jass normalisés
sb = np.where(jstm == 0, jn, -jn)
near = (nwk == nbk) & (np.abs(nwm - nbm) <= 1)
jd = jn.copy()
m1 = (sb > 0) & (nwk != 0)          # black ahead, white(loser) has king
jd[m1 & (nbm + nbk <= 3)] /= 8.0; jd[m1 & ~(nbm + nbk <= 3) & near] /= 2.0
m2 = (sb < 0) & (nbk != 0)          # white ahead, black(loser) has king
jd[m2 & (nwm + nwk <= 3)] /= 8.0; jd[m2 & ~(nwm + nwk <= 3) & near] /= 2.0
draw_applies = (m1 & ((nbm + nbk <= 3) | near)) | (m2 & ((nwm + nwk <= 3) | near))
def stats(mask, lbl):
    if mask.sum() < 30:
        return
    cc = lambda a: float(np.corrcoef(a[mask], ss[mask])[0, 1])
    rm = lambda a: float(np.sqrt(np.mean((a[mask] - ss[mask]) ** 2)))
    print(f"  {lbl:28s} n={int(mask.sum()):5d}  corr={cc(jn):+.3f} rmse={rm(jn):6.0f}  | +drawish corr={cc(jd):+.3f} rmse={rm(jd):6.0f}")
print(f"n={n}  (echelle jass alignee par regression sur Scan)")
stats(jpc <= 7, "<=7p (tout)")
stats((jpc <= 7) & draw_applies, "<=7p DRAWISH-applies")
stats((jpc <= 7) & ~draw_applies, "<=7p NON-drawish")
stats((jpc >= 8) & (jpc <= 14), "8-14p (tout)")
stats((jpc >= 8) & (jpc <= 14) & draw_applies, "8-14p DRAWISH-applies")
res = np.abs(jn - ss); fin = (jpc <= 10) & ~draw_applies
order = np.argsort(-(res * fin))
print("  --- pires desaccords finale NON-drawish (jass_norm vs scan) ---")
for i in order[:8]:
    if not fin[i]:
        break
    print(f"    pc={jpc[i]} wm{nwm[i]}wk{nwk[i]} bm{nbm[i]}bk{nbk[i]}  jass={jn[i]:.0f} scan={ss[i]:.0f} |res|={res[i]:.0f}")
PY
echo "=========================================================="
echo "  drawish REDUIT fort le rmse / monte la corr sur DRAWISH-applies -> c'est la brique (confirme 0351)."
echo "  Gros residu sur <=7p NON-drawish -> part QUALITE DES POIDS finale (pas un terme manquant)."
echo "=========================================================="
