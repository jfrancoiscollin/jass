#!/usr/bin/env bash
# id: 0173-drop-threshold-sweep
# description: NUIT #1 — sweep du SEUIL de score-drop sur v4 (1.4M). Le filtre
# (retirer |score|>4900) a fait le tournant (0.72→0.944). Un seuil plus serré
# (2000-4000) grappille-t-il encore ? Distill v4 par seuil, bench vs hc (108) +
# v15 (108). Base : v4+drop4900 = 0.944/0.389.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0173-drop-threshold-sweep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
for T in 2000 3000 4000 4900; do
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop $T --l2 1e-5 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --out "$ART/t$T.pjtw" >"$ART/t$T-train.log" 2>&1
  vm=$(grep -oE 'mse=[0-9.]+' "$ART/t$T-train.log"|head -1)
  ./build-prod/jass --benchmark-scan-eval "$ART/t$T.pjtw" hc 8 6 1 0 "" 64 >"$ART/t$T-hc.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/t$T.pjtw" "$V15" 9 6 1 0 "" 64 >"$ART/t$T-v15.log" 2>&1
  echo "  drop=$T : vs hc=$(rate "$ART/t$T-hc.log")  vs v15=$(rate "$ART/t$T-v15.log")  ($vm)"
  rm -f "$ART/t$T.pjtw"
done
echo "=========================================================="
echo "  0173 SEUIL DE DROP — VERDICT (vs hc/v15, 108 parties)"
for T in 2000 3000 4000 4900; do echo "  drop=$T : hc=$(rate "$ART/t$T-hc.log")  v15=$(rate "$ART/t$T-v15.log")"; done
echo "  base drop=4900 : 0.944 / 0.389 → meilleur seuil = gain gratuit."
echo "=========================================================="
