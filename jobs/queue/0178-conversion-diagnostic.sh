#!/usr/bin/env bash
# id: 0178-conversion-diagnostic
# description: LEVIER 1 — DIAGNOSTIC de la perte de conversion. Le champion
# (v4+106+drop4900+l2=1e-4) vaut 0.472 vs v15 à depth-fixe mais 0.382 à movetime.
# La connaissance d'éval est bonne ; elle ne se CONVERTIT pas en force au temps
# réel. Deux suspects (cf PATTERN_PROGRAM_NOTES §1) : search/time-mgmt réglés
# pour le régime NNUE (depth ~18), et instabilité de l'éval en profondeur.
#
#   (a) depth-at-movetime : à 300ms/1000ms, quelle profondeur atteint le pattern
#       vs v15 ? Confirme le décalage de régime (pattern depth 25-35 vs v15 ~18).
#   (b) ÉCHELLE rate(depth) : champion vs v15 à depth {7,9,11,13}. Si le taux
#       MONTE/stable avec la profondeur → éval stable, le problème est pur
#       time-mgmt (→ 0179 SPSA). Si le taux BAISSE en profondeur → l'éval se
#       dégrade quand on la cherche profond = instabilité (→ cause racine).
#
# expected_duration: ~1-1.5 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0178-conversion-diagnostic/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== (re)train champion (score, drop4900, l2=1e-4) ==="
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" 2>&1 | grep -E "score-drop|val   :"
[ -f "$ART/champ.pjtw" ] || { echo "ABORT train"; exit 7; }
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo; echo "=== (a) depth-at-movetime : champion vs v15 ==="
for MT in 300 1000; do
  ./build-prod/jass --depth-at-movetime "$ART/champ.pjtw" "$V15" $MT 64 2>&1 | tee "$ART/dam-$MT.log" | grep -iE "depth avg|A |B "
done

echo; echo "=== (b) échelle rate(depth) : champion vs v15 (108 parties/point) ==="
for D in 7 9 11 13; do
  ./build-prod/jass --benchmark-scan-eval "$ART/champ.pjtw" "$V15" $D 6 1 0 "" 64 >"$ART/d$D.log" 2>&1
  echo "  depth=$D : rate vs v15 = $(rate "$ART/d$D.log")"
done

echo; echo "=========================================================="
echo "        0178 DIAGNOSTIC CONVERSION — VERDICT"
echo "  profondeur atteinte (movetime) :"
echo "    300ms  : $(grep -iE 'depth avg' "$ART/dam-300.log"  | paste -sd' | ')"
echo "    1000ms : $(grep -iE 'depth avg' "$ART/dam-1000.log" | paste -sd' | ')"
echo "  rate(depth) vs v15 :"
for D in 7 9 11 13; do echo "    d$D = $(rate "$ART/d$D.log")"; done
echo "  réf : d9=0.472 (0176)  movetime=0.382"
echo "  → rate stable/montant en depth = time-mgmt (0179 SPSA payant)."
echo "  → rate qui BAISSE en depth = instabilité éval (cause racine à traiter)."
echo "=========================================================="
