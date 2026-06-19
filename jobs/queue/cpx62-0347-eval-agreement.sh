#!/usr/bin/env bash
# id: cpx62-0347-eval-agreement
# description: PHASE 2 — DIAGNOSTIC DÉCISIF. Notre éval-pattern (Scan-distillée) reproduit-elle l'éval de Scan ?
# Sur un set FORT INDÉPENDANT (corpus 0328 Scan-self-play, ≠ data d'entraînement 0314), on compare l'éval-jass
# (rewrite-scores avec le pjtw) à l'éval-Scan à d2 (≈ STATIQUE, la classe d'éval pure) ET d9 (la cible distillée),
# par phase. Bon accord → le linéaire FITTE Scan, le gap de 5 plies = erreurs fines (→ argument capacité).
# Mauvais accord → le linéaire NE PEUT PAS fitter Scan (capacité/patterns) = plafond de la classe linéaire.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/cpx62-0347-eval-agreement/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw   # train (0314, d9)
CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw  # set fort indépendant
SCAN_BIN=/root/jass-scan/scan_linux
N=20000
[ -f "$DATA" ] && [ -f "$CORPUS" ] || { echo "ABORT: data manquante"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "relabel Scan d2+d9 ${N} (×$NCPU) + corrélation" 80
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build + train éval (la même qu'on évalue partout) ==="
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

echo "=== set de test FORT indépendant : ${N} positions du corpus 0328 ==="
python3 - "$CORPUS" "$ART/test.jnnw" "$N" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
n=min(n,tot); st=max(1,tot//n); r=bytearray(); k=0
for i in range(0,tot,st):
    r+=body[i*REC:(i+1)*REC]; k+=1
    if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r)); print('test',k,'/',tot)
PY

echo "=== éval-jass sur le test (rewrite-scores avec le pjtw) ==="
"$JASS" --rewrite-scores-with-nnue "$ART/test.jnnw" "$ART/jass.jnnw" --nnue "$ART/eval.pjtw" >"$ART/rw.log" 2>&1
echo "=== éval-Scan d2 (≈ statique) et d9 (cible) ==="
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan_d2.jnnw" "$SCAN_BIN" 2 "$NCPU"
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan_d9.jnnw" "$SCAN_BIN" 9 "$NCPU"

echo "=== ACCORD éval-jass vs éval-Scan (Pearson/Spearman/RMSE, par phase) ==="
python3 - "$ART/jass.jnnw" "$ART/scan_d2.jnnw" "$ART/scan_d9.jnnw" <<'PY'
import sys,struct
import numpy as np
REC=38
def load(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    sc=np.empty(n,dtype=np.int32); pc=np.empty(n,dtype=np.int32); stm=np.empty(n,dtype=np.int8)
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]
        wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32])
        pc[i]=bin(wm).count("1")+bin(wk).count("1")+bin(bm).count("1")+bin(bk).count("1")
        stm[i]=rec[32]; sc[i]=struct.unpack('<i',rec[33:37])[0]
    return sc,pc,stm
js,jpc,jstm=load(sys.argv[1]); s2,_,_=load(sys.argv[2]); s9,_,_=load(sys.argv[3])
n=min(len(js),len(s2),len(s9)); js,s2,s9,jpc=js[:n],s2[:n],s9[:n],jpc[:n]
def spearman(a,b):
    ra=np.argsort(np.argsort(a)); rb=np.argsort(np.argsort(b)); 
    return float(np.corrcoef(ra,rb)[0,1])
def report(name,scan):
    # POV-align : essaie tel quel et avec flip stm, garde le meilleur (les conventions POV peuvent différer)
    best_p=-2; best=None
    for lab,jj in [("asis",js),("flip",np.where(jstm[:n]==0,js,-js))]:
        pass
    p=float(np.corrcoef(js.astype(float),scan.astype(float))[0,1]); sp=spearman(js,scan)
    pf=float(np.corrcoef(np.where(jstm[:n]==0,js,-js).astype(float),scan.astype(float))[0,1])
    if abs(pf)>abs(p): tag="(flip-POV)"; pear=pf
    else: tag=""; pear=p
    rmse=float(np.sqrt(np.mean((js-scan)**2)))
    print(f"  {name}: pearson={pear:+.3f}{tag}  spearman={sp:+.3f}  rmse={rmse:.0f}")
    for lo,hi,bn in [(2,7,'<=7p'),(8,15,'8-15p'),(16,25,'16-25p'),(26,50,'26+p')]:
        m=(jpc>=lo)&(jpc<=hi)
        if m.sum()>50:
            pp=float(np.corrcoef(js[m].astype(float),scan[m].astype(float))[0,1])
            print(f"      {bn:7s} n={int(m.sum()):5d}  pearson={pp:+.3f}")
print(f"n={n}")
report("vs Scan d2 (statique)", s2)
report("vs Scan d9 (cible)   ", s9)
PY
echo "=========================================================="
echo "  pearson/spearman ÉLEVÉ (>0.9) → le linéaire FITTE Scan → gap=erreurs fines (capacité)."
echo "  BAS / chute par phase → le linéaire NE PEUT PAS fitter Scan = plafond linéaire (patterns/capacité)."
echo "=========================================================="
