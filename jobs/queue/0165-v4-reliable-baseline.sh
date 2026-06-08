#!/usr/bin/env bash
# id: 0165-v4-reliable-baseline
# description: RESET → investigations point par point, étape 1 : RÉ-ÉTABLIR une
# baseline v4 FIABLE. Tous les benchs précédents = 54 parties (±0.07) → on a
# peut-être couru après du bruit. Ici on distille v4 (32 patterns, 106 extras)
# sur le 1.4M PROPRE (comme 0154) et on benche avec BEAUCOUP de parties pour
# une vraie référence : vs hc 180 parties (±0.037), vs v15 144 parties.
#
# But : confirmer que v4 vaut bien ~0.75 vs hc (et non du bruit), et figer une
# baseline solide contre laquelle comparer chaque changement futur (1 à la fois).
#
# expected_duration: ~1-1.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0165-v4-reliable-baseline"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU  RAM: $(free -g 2>/dev/null | awk '/Mem/{print $2"G"}') ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: 1.4M propre (0141) absent — purgé ?"; exit 3; }
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$CLEAN','rb').read(8),4)[0])")
echo "1.4M propre : $CLEAN ($NB records)"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v4 32 patterns, 106 extras) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns as p;print('NUM_PATTERNS',p.NUM_PATTERNS,'(doit être 32)')"

echo; echo "=== dump features (106) + distill v4 config A (l2 1e-5, material-anchor) ==="
FEAT=/root/jass/jobs/results/0147-scan-eval-full/artefacts.src/clean.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v4.pjtw" 2>&1 \
    | tee "$ART/train.log" | grep -E "val   :|design|material-anchor"

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
ngames () { grep -oE 'total [0-9]+' "$1" 2>/dev/null | grep -oE '[0-9]+' | head -1; }

echo; echo "=== BENCHS FIABLES (beaucoup de parties) ==="
echo "--- vs handcrafted, depth 8, 10 paires (180 parties) ---"
./build-prod/jass --benchmark-scan-eval "$ART/v4.pjtw" hc 8 10 1 0 "" 64 2>&1 | tee "$ART/vs-hc.log" | grep -E "Result|rate"
echo "--- vs v15, depth 9, 8 paires (144 parties) ---"
./build-prod/jass --benchmark-scan-eval "$ART/v4.pjtw" "$V15" 9 8 1 0 "" 64 2>&1 | tee "$ART/vs-v15-d9.log" | grep -E "Result|rate"
echo "--- vs v15, movetime 300, 8 paires (144 parties) ---"
./build-prod/jass --benchmark-scan-eval "$ART/v4.pjtw" "$V15" 64 8 1 300 "" 64 2>&1 | tee "$ART/vs-v15-mt.log" | grep -E "Result|rate"

echo; echo "=========================================================="
echo "        0165 BASELINE v4 FIABLE — VERDICT"
echo "  vs hc       : $(anyrate "$ART/vs-hc.log")  ($(ngames "$ART/vs-hc.log") parties, ±0.037)"
echo "  vs v15 d9   : $(anyrate "$ART/vs-v15-d9.log")  ($(ngames "$ART/vs-v15-d9.log") parties)"
echo "  vs v15 mt   : $(anyrate "$ART/vs-v15-mt.log")  ($(ngames "$ART/vs-v15-mt.log") parties)"
echo "  (rappel bruité 0154 : vs hc 0.75 sur 54 parties)"
echo "  → fige la VRAIE référence v4 pour les investigations point par point."
echo "=========================================================="
