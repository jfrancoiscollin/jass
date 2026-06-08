#!/usr/bin/env bash
# id: 0174-l2-resweep-with-drop
# description: NUIT #2 — re-sweep l2 AVEC le filtre. 0167 avait trouvé l2=1e-5
# optimal, MAIS sur baseline EMPOISONNÉ (le poison faisait sur-apprendre à bas
# l2). Avec score-drop 4900, l'optimum a peut-être bougé. Sweep l2 sur v4+1.4M+
# drop, bench vs hc (108) + v15 (108). Base : l2=1e-5+drop = 0.944/0.389.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0174-l2-resweep-with-drop/artefacts.src"; mkdir -p "$ART"
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
for L in 1e-6 1e-5 1e-4 1e-3; do
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 $L --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --out "$ART/l$L.pjtw" >"$ART/l$L-train.log" 2>&1
  vm=$(grep -oE 'mse=[0-9.]+' "$ART/l$L-train.log"|head -1)
  ./build-prod/jass --benchmark-scan-eval "$ART/l$L.pjtw" hc 8 6 1 0 "" 64 >"$ART/l$L-hc.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/l$L.pjtw" "$V15" 9 6 1 0 "" 64 >"$ART/l$L-v15.log" 2>&1
  echo "  l2=$L : vs hc=$(rate "$ART/l$L-hc.log")  vs v15=$(rate "$ART/l$L-v15.log")  ($vm)"
  rm -f "$ART/l$L.pjtw"
done
echo "=========================================================="
echo "  0174 l2 AVEC FILTRE — VERDICT (l'optimum a-t-il bougé vs le poison ?)"
for L in 1e-6 1e-5 1e-4 1e-3; do echo "  l2=$L : hc=$(rate "$ART/l$L-hc.log")  v15=$(rate "$ART/l$L-v15.log")"; done
echo "  base l2=1e-5 : 0.944 / 0.389"
echo "=========================================================="
