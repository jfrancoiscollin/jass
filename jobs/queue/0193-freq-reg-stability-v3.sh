#!/usr/bin/env bash
# id: 0193-freq-reg-stability-v3
# description: PISTE A (3e tentative, infra robuste) — freq-reg sur v6 corrige-t-
# elle l'instabilité profondeur ? Échecs précédents = INFRA : le runner reverte
# les fichiers source modifiés (patterns.py) vers HEAD=32 à chaque commit de
# heartbeat → les distills après le 1er heartbeat utilisaient 32 (pjtw illisible
# par le binaire v6/40). FIX : ré-émettre v6 JUSTE AVANT chaque distill (train.py
# importe patterns.py au démarrage ; un revert ultérieur n'affecte pas le train
# en cours). CCACHE_DISABLE + retry pour le build (cf 0191).
#
# réf v6 plein (0188/0192 control) : d9=0.556 → d13=0.389 (dégrade).
# Sweep --freq-reg ∈ {0,0.3,3.0}, mesure d9 vs d13 + movetime.
# expected_duration: ~2-2.5 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0193-freq-reg-stability-v3/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
export CCACHE_DISABLE=1
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
emit_v6(){ python3 pattern_jass/tools/gen_patterns.py --variant v6 --emit >/dev/null 2>&1; }

echo "=== émettre v6 + build (binaire = 40 patterns) ==="
emit_v6
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || {
  echo "build retry"; rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >>"$ART/cmake.log" 2>&1
  cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || echo "TESTS note"
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1

for S in 0 0.3 3.0; do
  echo; echo "=== freq-reg=$S ==="
  emit_v6   # garantit patterns.py=40 au démarrage de CE train (anti-revert heartbeat)
  EXTRA=""; [ "$S" != "0" ] && EXTRA="--freq-reg $S"
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 $EXTRA --out "$ART/s$S.pjtw" \
    >"$ART/train-$S.log" 2>&1
  grep -E "design|freq-reg|val   :" "$ART/train-$S.log" | sed 's/^/    /'
  [ -f "$ART/s$S.pjtw" ] || { echo "  ABORT train $S"; continue; }
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/s$S-d9.log"  2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 13 6 1 0   "" 64 >"$ART/s$S-d13.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/s$S.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/s$S-mt.log"  2>&1
  echo "  freq-reg=$S : d9=$(rate "$ART/s$S-d9.log")  d13=$(rate "$ART/s$S-d13.log")  mt=$(rate "$ART/s$S-mt.log")"
done

echo; echo "=========================================================="
echo "        0193 FREQ-REG (piste A) — VERDICT (sur v6)"
for S in 0 0.3 3.0; do
  echo "  freq-reg=$S : d9=$(rate "$ART/s$S-d9.log")  d13=$(rate "$ART/s$S-d13.log")  mt=$(rate "$ART/s$S-mt.log")"
done
echo "  réf v6 plein : d9=0.556 → d13=0.389 (dégrade)"
echo "  → un S où d13≈d9 SANS écrouler d9 = famine corrigée proprement → éval riche STABLE."
echo "  → sinon → piste A épuisée → B (recul stratégique)."
echo "=========================================================="
