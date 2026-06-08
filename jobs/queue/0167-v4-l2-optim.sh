#!/usr/bin/env bash
# id: 0167-v4-l2-optim
# description: INVESTIGATION #3 — optimiser l2 sur v4 (32 patterns). 0166 a
# montré que v4 est TRÈS sensible à l2 et que le faible l2 gagne (1e-5=0.72,
# 1e-4=0.50, 1e-3=0.39). On descend SOUS 1e-5 pour trouver le pic : possible
# gain gratuit (juste un hyperparamètre). Distillation sur le 1.4M PROPRE,
# bench vs hc 144 parties (±0.042) par l2, puis bench FIABLE (216) + vs v15 sur
# le meilleur.
#
# Référence (0165/0166) : v4 l2=1e-5 = 0.72 vs hc.
# Lecture : un l2 plus bas qui dépasse 0.72 = gain ; sinon 1e-5 est l'optimum
# (et trop bas → sur-apprentissage des buckets sparses).
#
# expected_duration: ~1.5-2 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0167-v4-l2-optim"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: 1.4M propre (0141) absent"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v4 32 patterns) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns as p;print('NUM_PATTERNS',p.NUM_PATTERNS,'(=32)')"
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

FEAT=/root/jass/jobs/results/0147-scan-eval-full/artefacts.src/clean.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

distill () {  # $1 l2  → writes $ART/l2$1.pjtw, echoes nothing
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$1" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/l2$1.pjtw" > "$ART/l2$1-train.log" 2>&1
}

echo; echo "=== SWEEP l2 (vs hc, 144 parties) ==="
for l2 in 1e-7 3e-7 1e-6 3e-6 1e-5; do
    distill "$l2"
    vm=$(grep -oE "mse=[0-9.]+" "$ART/l2$l2-train.log" | head -1)
    if [ -f "$ART/l2$l2.pjtw" ]; then
        ./build-prod/jass --benchmark-scan-eval "$ART/l2$l2.pjtw" hc 8 8 1 0 "" 64 > "$ART/l2$l2-vs-hc.log" 2>&1
        echo "  l2=$l2 : vs hc=$(anyrate "$ART/l2$l2-vs-hc.log")  ($vm)"
    else
        echo "  l2=$l2 : ÉCHEC train"
    fi
done

# meilleur l2
BEST=$(for l2 in 1e-7 3e-7 1e-6 3e-6 1e-5; do echo "$(anyrate "$ART/l2$l2-vs-hc.log") $l2"; done | sort -rn | head -1 | awk '{print $2}')
echo; echo "=== meilleur l2 = $BEST → bench FIABLE (216 vs hc) + vs v15 ==="
./build-prod/jass --benchmark-scan-eval "$ART/l2$BEST.pjtw" hc 8 12 1 0 "" 64 > "$ART/best-vs-hc.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/l2$BEST.pjtw" "$V15" 9 8 1 0 "" 64 > "$ART/best-vs-v15-d9.log" 2>&1
for l2 in 1e-7 3e-7 1e-6 3e-6 1e-5; do [ "$l2" != "$BEST" ] && rm -f "$ART/l2$l2.pjtw"; done

echo; echo "=========================================================="
echo "        0167 OPTIM l2 sur v4 — VERDICT"
echo "  (réf 0165 fiable : v4 l2=1e-5 = 0.72)"
for l2 in 1e-7 3e-7 1e-6 3e-6 1e-5; do
  echo "  l2=$l2 : vs hc(144)=$(anyrate "$ART/l2$l2-vs-hc.log")"
done
echo "  MEILLEUR l2=$BEST : vs hc(216 fiable)=$(anyrate "$ART/best-vs-hc.log")  vs v15 d9=$(anyrate "$ART/best-vs-v15-d9.log")"
echo "  → > 0.72 = gain gratuit (nouveau l2 optimal) ; ≈0.72 = 1e-5 confirmé."
echo "=========================================================="
