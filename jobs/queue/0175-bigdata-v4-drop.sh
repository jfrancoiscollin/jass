#!/usr/bin/env bash
# id: 0175-bigdata-v4-drop
# description: NUIT #3 — plus de data PROPRE sur base saine. v4 (32) sur le
# master 4.70M AVEC score-drop 4900, benchs FIABLES vs hc (144) + v15 (144) +
# v15 movetime (72). 0170 (4.7M+drop, 106 extras) = 0.833/0.417 — refait propre
# (extras courants) + le régime movetime. > 1.4M+drop (0.944/0.389) vs v15 = la
# data clean aide vers v15.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0175-bigdata-v4-drop/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "RAM: $(free -g 2>/dev/null|awk '/Mem/{print $2}')G"
BIG=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$BIG" ] || { echo "ABORT 4.7M absent"; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$BIG" "$FEAT" 2>&1 | tail -1
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }
python3 pattern_jass/tools/train.py --data "$BIG" --scan-eval --eval-features-file "$FEAT" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-5 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --out "$ART/v4big.pjtw" 2>&1 | tee "$ART/train.log" | grep -E "score-drop|val   :|split"
[ -f "$ART/v4big.pjtw" ] || { echo "ABORT train"; exit 7; }
./build-prod/jass --benchmark-scan-eval "$ART/v4big.pjtw" hc 8 8 1 0 "" 64 >"$ART/vs-hc.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v4big.pjtw" "$V15" 9 8 1 0 "" 64 >"$ART/vs-v15-d9.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v4big.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/vs-v15-mt.log" 2>&1
echo "=========================================================="
echo "  0175 DATA 4.7M + drop sur v4 — VERDICT"
echo "  v4/4.7M+drop : vs hc=$(rate "$ART/vs-hc.log")  vs v15 d9=$(rate "$ART/vs-v15-d9.log")  mt=$(rate "$ART/vs-v15-mt.log")"
echo "  base v4/1.4M+drop : 0.944 / 0.389"
echo "  → vs v15 > 0.389 = la data clean aide vers v15 (scaler) ; sinon 1.4M suffit."
echo "=========================================================="
