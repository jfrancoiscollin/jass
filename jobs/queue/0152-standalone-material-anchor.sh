#!/usr/bin/env bash
# id: 0152-standalone-material-anchor
# description: RÉPARATION du standalone (branche choisie). Le diagnostic 0151 a
# montré : v3 standalone perd 0/N vs handcrafted, matériel mal signé en MG
# (men-count colinéaire avec les patterns → sur buckets non vus, l'éval retombe
# sur un matériel faux). Fix : ANCRER le matériel (homme≈+1, roi≈+3) via un L2
# par-colonne → les patterns apprennent le RÉSIDU positionnel sur une fondation
# matérielle stable, tout en restant STANDALONE (pas de squelette séparé).
#
# On entraîne 2 configs (le jouet a montré que des patterns trop libres ±2.5pu
# écrasent le matériel ±1-3pu → tester un L2 plus fort qui dompte les patterns) :
#   A : material-anchor 1.0, l2 1e-5  (patterns libres)
#   B : material-anchor 1.0, l2 1e-3  (patterns domptés, matériel domine plus)
# Puis triangle (vs hc, vs v15) + sonde matériel sur chaque.
# Lecture : si A ou B BAT hc → le fix marche, on poursuit (fine-tune/cycles) ;
#           si les deux perdent encore → patterns nuisibles → revoir features/l2.
#
# expected_duration: ~45-70 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0152-standalone-material-anchor"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: labels 0141 manquants"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "labels: $CLEAN"; echo "v15: $V15"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump-eval-features (réutilise 0147 si présent) ==="
FEAT=/root/jass/jobs/results/0147-scan-eval-full/artefacts.src/clean.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
echo "feat: $FEAT"

probe () { python3 - "$1" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0);o=20
pm=np.frombuffer(raw,'<i4',np_,o);o+=4*np_;pe=np.frombuffer(raw,'<i4',np_,o);o+=4*np_
em=np.frombuffer(raw,'<i4',ne,o);o+=4*ne;ee=np.frombuffer(raw,'<i4',ne,o)
print(f"    HOMMES mg b={em[100]/s:+.2f} w={em[101]/s:+.2f} | ROIS mg b_moy={(em[0:50]/s).mean():+.2f}"
      f" | PAT |w|max={np.abs(pm).max()/s:.2f}pu nnz={(pm!=0).sum()}")
PYEOF
}
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_one () {  # $1 tag  $2 l2  -> writes $ART/$tag.pjtw
    local tag="$1" l2="$2"
    echo; echo "=== TRAIN $tag (material-anchor 1.0, l2=$l2) ==="
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$l2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" 2>&1 | tee "$ART/$tag-train.log" | grep -E "val   :|material-anchor|quant"
    probe "$ART/$tag.pjtw"
}

train_one A 1e-5
train_one B 1e-3

echo; echo "=== TRIANGLE : chaque config vs handcrafted (depth 8) ==="
for tag in A B; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")"
done
./build-prod/jass --benchmark-nnue "$V15" 8 3 1 0 2>&1 | tee "$ART/v15-vs-hc.log" >/dev/null
echo "  v15 vs hc = $(anyrate "$ART/v15-vs-hc.log")"

# meilleur des deux vs v15 (depth + movetime court)
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B
echo; echo "=== meilleur ($BEST) vs v15 (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"

echo; echo "=========================================================="
echo "        0152 STANDALONE MATERIAL-ANCHOR — LECTURE"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}  v15 vs hc=$(anyrate "$ART/v15-vs-hc.log")"
echo "  → un v3 ancré qui BAT hc = fondation réparée ; sinon patterns nuisibles."
echo "=========================================================="
