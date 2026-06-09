#!/usr/bin/env bash
# id: 0179-spsa-highdepth-regime
# description: LEVIER 2 — SPSA du search/time-mgmt POUR LE RÉGIME HAUTE PROFONDEUR
# du pattern. Les heuristiques (LMR/LMP/RFP/NMP/razor/probcut...) ont été réglées
# sur v15 (depth ~18). Le pattern, ~100× plus rapide, atteint depth 25-35 en
# movetime — un régime différent. On tune SPSA directement À MOVETIME sur le
# champion, puis on valide le meilleur spec vs défaut (movetime fiable + depth).
#
#   Hypothèse : un search réglé pour le bon régime convertit la connaissance
#   (0.472 depth-fixe) en force réelle (>0.382 movetime). Elo "gratuit" via la
#   vitesse, orthogonal à la capacité d'éval.
#
# expected_duration: ~2.5-3.5 h (SPSA = beaucoup de mini-matchs).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0179-spsa-highdepth-regime/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== (re)train champion ==="
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" 2>&1 | grep -E "score-drop|val   :"
[ -f "$ART/champ.pjtw" ] || { echo "ABORT train"; exit 7; }
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo; echo "=== SPSA à MOVETIME 300ms (self-play du champion, 70 iters) ==="
BEST_JSON="$ART/spsa-best.json"
python3 tools/spsa_tune.py --jass ./build-prod/jass --net "$ART/champ.pjtw" \
  --iters 70 --pairs 4 --threads 1 --movetime-ms 300 --use-pvs 1 --a0 2.0 --seed 1 \
  --out "$BEST_JSON" 2>&1 | tee "$ART/spsa.log" | tail -8
BEST=$(python3 -c "import json;print(json.load(open('$BEST_JSON'))['spec'])" 2>/dev/null)
echo "  best spec : $BEST"

echo; echo "=== validation : spec tuné vs défaut (movetime 300ms, fiable) ==="
# benchmark-search-params : <net> <specA> <specB> <depth> <pairs> <thr> <movetime> ...
./build-prod/jass --benchmark-search-params "$ART/champ.pjtw" "$BEST" "" 64 8 1 300 2>&1 | tee "$ART/tuned-vs-default-mt.log" | grep -iE "rate|result"
echo; echo "=== le champion TUNÉ vs v15 (movetime 72 + depth d9 144) ==="
./build-prod/jass --benchmark-scan-eval "$ART/champ.pjtw" "$V15" 64 4 1 300 "$BEST" 64 >"$ART/tuned-vs-v15-mt.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/champ.pjtw" "$V15" 9  8 1 0   "$BEST" 64 >"$ART/tuned-vs-v15-d9.log" 2>&1

echo; echo "=========================================================="
echo "        0179 SPSA HAUTE-PROFONDEUR — VERDICT"
echo "  best spec : $BEST"
echo "  tuné vs défaut (movetime)        : $(rate "$ART/tuned-vs-default-mt.log")  (>0.5 = le tuning aide)"
echo "  champion tuné vs v15 movetime    : $(rate "$ART/tuned-vs-v15-mt.log")"
echo "  champion tuné vs v15 d9          : $(rate "$ART/tuned-vs-v15-d9.log")"
echo "  réf champion DÉFAUT : v15 movetime=0.382  d9=0.472"
echo "  → movetime vs v15 > 0.382 = le search réglé convertit la connaissance."
echo "=========================================================="
