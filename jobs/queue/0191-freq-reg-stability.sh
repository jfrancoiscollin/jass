#!/usr/bin/env bash
# id: 0191-freq-reg-stability
# description: PISTE A — la RÉGULARISATION PONDÉRÉE PAR FRÉQUENCE corrige-t-elle
# l'instabilité en profondeur de v6, LÀ OÙ le hashing a échoué (0190 : collisions
# → connaissance détruite) ? freq-reg tire SEULEMENT les buckets rares (sous-
# entraînés, ~99% des buckets) vers 0 = strength/(visits+1), en laissant les
# buckets communs (la connaissance) intacts. Pas de collision.
#
# Sur v6 (PATTERN_HASH plein), sweep --freq-reg ∈ {0(control),0.03,0.3,3.0},
# mesure rate(depth) d9 vs d13 + movetime vs v15.
#
#   d13 cesse de chuter SANS tuer d9 = famine = cause confirmée ET corrigée
#     proprement → éval riche STABLE en profondeur (reste la vitesse à régler).
#   d9 s'écroule comme avec le hashing, ou d13 chute encore = freq-reg n'aide pas
#     → passer à B (recul stratégique).
#
# réf v6 plein (0188) : d9=0.556 → d13=0.389 (dégrade).
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0191-freq-reg-stability/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo "=== émettre v6 (diagonale dense, 40 patterns) — PATTERN_HASH plein ==="
python3 pattern_jass/tools/gen_patterns.py --variant v6 --emit >"$ART/emit.log" 2>&1
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp
grep -m1 "constexpr std::uint32_t PATTERN_HASH" pattern_jass/src/pattern.hpp
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1

for S in 0 0.03 0.3 3.0; do
  echo; echo "=== freq-reg=$S ==="
  EXTRA=""; [ "$S" != "0" ] && EXTRA="--freq-reg $S"
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 $EXTRA --out "$ART/s$S.pjtw" \
    >"$ART/train-$S.log" 2>&1
  grep -E "freq-reg|val   :" "$ART/train-$S.log" | sed 's/^/    /'
  [ -f "$ART/s$S.pjtw" ] || { echo "  ABORT train $S"; continue; }
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/s$S-d9.log"  2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 13 6 1 0   "" 64 >"$ART/s$S-d13.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/s$S-mt.log"  2>&1
  echo "  freq-reg=$S : d9=$(rate "$ART/s$S-d9.log")  d13=$(rate "$ART/s$S-d13.log")  mt=$(rate "$ART/s$S-mt.log")"
done

echo; echo "=========================================================="
echo "        0191 FREQ-REG (piste A) — VERDICT (sur v6)"
for S in 0 0.03 0.3 3.0; do
  echo "  freq-reg=$S : d9=$(rate "$ART/s$S-d9.log")  d13=$(rate "$ART/s$S-d13.log")  mt=$(rate "$ART/s$S-mt.log")"
done
echo "  réf v6 plein (0188) : d9=0.556 → d13=0.389 (dégrade)"
echo "  → un S où d13≈d9 (haut) = famine corrigée proprement → éval riche STABLE."
echo "  → d9 s'écroule / d13 chute toujours = freq-reg n'aide pas → on passe à B."
echo "=========================================================="
