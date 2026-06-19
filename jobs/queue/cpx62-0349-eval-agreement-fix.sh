#!/usr/bin/env bash
# id: cpx62-0349-eval-agreement-fix
# description: 0347 CORRIGÉ. Le bug de 0347 : le relabel DROPPE ~17% des positions → scores-jass (sur l'original)
# et scores-Scan (sous-ensemble réordonné) DÉSALIGNÉS → corrélation ~0 spurious. FIX : on relabel d'abord
# (Scan d2 + d9), PUIS on calcule l'éval-jass SUR CES fichiers relabelisés (mêmes positions, même ordre) →
# aligné. Mesure réelle de l'accord éval-jass / éval-Scan, par phase. (POV géré par flip-check.)
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
source jobs/lib/relabel.sh
ART="/root/jass/jobs/results/cpx62-0349-eval-agreement-fix/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
CORPUS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
N=20000
[ -f "$DATA" ] && [ -f "$CORPUS" ] || { echo "ABORT: data manquante"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "relabel Scan d2+d9 ${N} + corrélation alignée" 80
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

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

echo "=== test set ${N} (corpus 0328) ==="
python3 - "$CORPUS" "$ART/test.jnnw" "$N" <<'PY'
import sys,struct
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; body=b[8:]
n=min(n,tot); st=max(1,tot//n); r=bytearray(); k=0
for i in range(0,tot,st):
    r+=body[i*REC:(i+1)*REC]; k+=1
    if k>=n: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+bytes(r))
PY

echo "=== relabel Scan d2 + d9 (chacun son sous-ensemble) ==="
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan_d2.jnnw" "$SCAN_BIN" 2 "$NCPU"
relabel_scan_sharded "$ART/test.jnnw" "$ART/scan_d9.jnnw" "$SCAN_BIN" 9 "$NCPU"
echo "=== éval-jass SUR les fichiers relabelisés (ALIGNÉ : mêmes positions, même ordre) ==="
"$JASS" --rewrite-scores-with-nnue "$ART/scan_d2.jnnw" "$ART/jass_on_d2.jnnw" --nnue "$ART/eval.pjtw" >>"$ART/rw.log" 2>&1
"$JASS" --rewrite-scores-with-nnue "$ART/scan_d9.jnnw" "$ART/jass_on_d9.jnnw" --nnue "$ART/eval.pjtw" >>"$ART/rw.log" 2>&1

echo "=== ACCORD (aligné) éval-jass vs éval-Scan ==="
python3 - "$ART/jass_on_d2.jnnw" "$ART/scan_d2.jnnw" "$ART/jass_on_d9.jnnw" "$ART/scan_d9.jnnw" <<'PY'
import sys,struct
import numpy as np
REC=38
def load(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    sc=np.empty(n,dtype=np.int32); pc=np.empty(n,dtype=np.int32); stm=np.empty(n,dtype=np.int8)
    bbs=np.empty((n,4),dtype=np.uint64)
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<4Q',rec[0:32])
        bbs[i]=(wm,wk,bm,bk); pc[i]=bin(wm).count("1")+bin(wk).count("1")+bin(bm).count("1")+bin(bk).count("1")
        stm[i]=rec[32]; sc[i]=struct.unpack('<i',rec[33:37])[0]
    return sc,pc,stm,bbs
def spearman(a,b):
    return float(np.corrcoef(np.argsort(np.argsort(a)),np.argsort(np.argsort(b)))[0,1])
def report(name,jp,sp):
    js,jpc,jstm,jbb=load(jp); ss,spc,sstm,sbb=load(sp)
    n=min(len(js),len(ss)); assert (jbb[:n]==sbb[:n]).all(), "MISALIGNED bitboards!"
    js,ss,jpc,jstm=js[:n],ss[:n],jpc[:n],jstm[:n]
    p=float(np.corrcoef(js.astype(float),ss.astype(float))[0,1])
    pf=float(np.corrcoef(np.where(jstm==0,js,-js).astype(float),ss.astype(float))[0,1])
    pear=pf if abs(pf)>abs(p) else p; tag="(flip-POV)" if abs(pf)>abs(p) else ""
    print(f"  {name}: pearson={pear:+.3f}{tag}  spearman={spearman(js,ss):+.3f}  n={n}")
    for lo,hi,bn in [(2,7,'<=7p'),(8,15,'8-15p'),(16,25,'16-25p'),(26,50,'26+p')]:
        m=(jpc>=lo)&(jpc<=hi)
        if m.sum()>50:
            jj=np.where(jstm[m]==0,js[m],-js[m]) if abs(pf)>abs(p) else js[m]
            print(f"      {bn:7s} n={int(m.sum()):5d}  pearson={float(np.corrcoef(jj.astype(float),ss[m].astype(float))[0,1]):+.3f}")
report("vs Scan d2 (statique)", sys.argv[1], sys.argv[2])
report("vs Scan d9 (cible)   ", sys.argv[3], sys.argv[4])
PY
echo "=========================================================="
echo "  ALIGNEMENT vérifié (assert bitboards). pearson élevé → linéaire fitte Scan. bas → plafond."
echo "=========================================================="
