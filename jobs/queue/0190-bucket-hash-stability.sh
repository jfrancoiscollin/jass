#!/usr/bin/env bash
# id: 0190-bucket-hash-stability
# description: PISTE 3 — le hashing de buckets corrige-t-il l'INSTABILITÉ EN
# PROFONDEUR ? 0188 : v6 (diagonale, riche) DÉGRADE avec la profondeur
# (0.556 d9 → 0.389 d13) — soupçon : buckets affamés donnant du garbage sur les
# positions rares que la recherche profonde atteint. Le hashing (PATTERN_HASH)
# réduit les buckets/pattern → bien mieux entraînés → stables.
#
# Sur la géométrie v6, on balaie PATTERN_HASH ∈ {531441(plein), 16384, 4096} et
# on mesure rate(depth) d9 vs d13 (le signal de dégradation) + movetime vs v15.
#
#   d13 cesse de chuter sous le hashing = famine confirmée ET corrigée (piste 3
#   vivante : on tient la connaissance de v6 jusqu'en profondeur).
#   d13 chute encore = le hashing ne suffit pas (autre cause d'instabilité).
#
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0190-bucket-hash-stability/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo "=== émettre la géométrie v6 (diagonale dense, 40 patterns) ==="
python3 pattern_jass/tools/gen_patterns.py --variant v6 --emit >"$ART/emit.log" 2>&1
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp

for H in 531441 16384 4096; do
  echo; echo "=== PATTERN_HASH=$H ==="
  sed -i -E "s/(PATTERN_HASH +)= [0-9]+;/\\1= ${H};/" pattern_jass/src/pattern.hpp
  sed -i -E "s/^(PATTERN_HASH +)= .*/\\1= ${H}/" pattern_jass/tools/patterns.py
  grep -m1 "constexpr std::uint32_t PATTERN_HASH" pattern_jass/src/pattern.hpp
  rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake-$H.log" 2>&1
  cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build-$H.log" 2>&1 || { echo "BUILD FAIL $H"; tail -15 "$ART/build-$H.log"; continue; }
  ./build-prod/jass_tests >"$ART/tests-$H.log" 2>&1 && echo "  tests OK" || echo "  TESTS FAIL"
  ./build-prod/jass --dump-eval-features "$CLEAN" "$ART/feat-$H" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/feat-$H" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/h$H.pjtw" >"$ART/train-$H.log" 2>&1
  [ -f "$ART/h$H.pjtw" ] || { echo "  ABORT train $H"; continue; }
  ./build-prod/jass --benchmark-scan-eval "$ART/h$H.pjtw" "$V15" 9  8 1 0   "" 64 >"$ART/h$H-d9.log"  2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/h$H.pjtw" "$V15" 13 8 1 0   "" 64 >"$ART/h$H-d13.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/h$H.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/h$H-mt.log"  2>&1
  echo "  H=$H : d9=$(rate "$ART/h$H-d9.log")  d13=$(rate "$ART/h$H-d13.log")  mt=$(rate "$ART/h$H-mt.log")"
done

echo; echo "=========================================================="
echo "        0190 HASHING DE BUCKETS (piste 3) — VERDICT (sur v6)"
for H in 531441 16384 4096; do
  echo "  H=$H : d9=$(rate "$ART/h$H-d9.log")  d13=$(rate "$ART/h$H-d13.log")  mt=$(rate "$ART/h$H-mt.log")"
done
echo "  réf v6 plein (0188) : d9=0.556 → d13=0.389 (dégrade)"
echo "  → d13 remonte/tient sous hashing = famine corrigée → connaissance stable"
echo "    en profondeur → reste à la convertir (vitesse / movegen)."
echo "  → d13 chute encore = autre cause (calibration/échelle), pas la famine."
echo "=========================================================="
