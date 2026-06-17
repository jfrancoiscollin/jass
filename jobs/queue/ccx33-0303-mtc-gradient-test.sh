#!/usr/bin/env bash
# id: ccx33-0303-mtc-gradient-test
# description: VALIDATION end-to-end de la labellisation-gradient (chaîne complète). (1) gen-egdb-wld
# 150k coverage ≤7 (labels WLD exacts). (2) --egdb-mtc-relabel → score = prob graduée par distance MTC
# (WDL pour la masse, graduée en finale). (3) check distribution. (4) dump-features + train --target prob
# --loss logistic (lit score/10000 comme cible) → confirme que ça s'entraîne + le nb de cibles graduées.
# Si OK → la chaîne gradient est prête ; on décide ensuite d'un vrai run d'entraînement gradient.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0303-mtc-gradient-test/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
ls "$MTC"/*.idx_mtc >/dev/null 2>&1 || { echo "ABORT: MTC absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=./build-egdb/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo "=== (1) coverage ≤7 (150k) ==="
$JASS --gen-egdb-wld 150000 "$ART/cov.jnnw" "$WLD" 7 512 4242 2>&1 | tail -1
echo "=== (2) mtc-relabel → score = prob graduée ==="
$JASS --egdb-mtc-relabel "$ART/cov.jnnw" "$WLD" "$MTC" "$ART/cov-grad.jnnw" 1024 2>&1 | tail -1
echo "=== (3) distribution du score (prob*10000) ==="
python3 - "$ART/cov-grad.jnnw" <<'PY'
import sys,struct,collections,numpy as np
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38
sc=np.array([struct.unpack_from('<i',body,i*REC+33)[0] for i in range(n)],dtype=np.float64)/10000.0
c=collections.Counter()
for v in sc:
    if v==1.0: c['win(1.0)']+=1
    elif v==0.0: c['loss(0.0)']+=1
    elif v==0.5: c['draw(0.5)']+=1
    elif v>0.5: c['win-graded(0.55-0.99)']+=1
    else: c['loss-graded(0.01-0.45)']+=1
print('  prob target distribution:',dict(c))
g=sc[(sc>0.5)&(sc<1.0)]
if len(g): print(f'  win-graded: n={len(g)} range[{g.min():.3f}..{g.max():.3f}] mean {g.mean():.3f}')
PY
echo "=== (4) train --target prob --loss logistic (petit, lowmem) ==="
$JASS --dump-eval-features "$ART/cov-grad.jnnw" "$ART/featG" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$ART/cov-grad.jnnw" --scan-eval --king-patterns \
  --eval-features-file "$ART/featG" --loss logistic --target prob --l2 3e-4 --max-iter 80 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/grad.pjtw" >"$ART/grad-train.log" 2>&1
[ -f "$ART/grad.pjtw" ] && echo "TRAIN OK → grad.pjtw" || { echo "TRAIN FAIL"; tail -12 "$ART/grad-train.log"; exit 7; }
grep -iE 'PROB target|graded|val/phase|train_loss' "$ART/grad-train.log" | head -6

echo; echo "=========================================================="
echo "   ccx33-0303 — VALIDATION chaîne gradient (mtc-relabel + --target prob)"
echo "  distribution graduée présente + TRAIN OK → la chaîne est prête."
echo "  SUITE : vrai run gradient (coverage enrichie en ≥10-MTC + self-play) vs baseline → conversion."
echo "=========================================================="
