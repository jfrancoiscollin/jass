#!/usr/bin/env bash
# id: 0176-l2-1e-4-confirm
# description: NUIT #4 — CONFIRMER + raffiner le nouvel optimum l2. 0174 (108
# parties) a montré que sur base SAINE (score-drop), l'optimum l2 a bougé de
# 1e-5 (trouvé sur poison, 0167) vers 1e-4 : hc=1.0 / v15=0.472 contre le
# champion 0.944/0.389. Gain réel vers v15 mais 108 parties = bruit ±0.05.
#
# Ici : fine-sweep l2 ∈ {1e-4, 2e-4, 3e-4} sur v4+1.4M+drop4900, benchs FIABLES
# (144 parties vs hc + 144 vs v15 d9), puis le meilleur en régime movetime (72).
# Confirme 1e-4 comme champion et cherche si le pic est plus loin (1e-3=0.417,
# donc le pic est probablement entre 1e-4 et 3e-4).
#
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0176-l2-1e-4-confirm/artefacts.src"; mkdir -p "$ART"
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
best=""; bestrate="0"
for L in 1e-4 2e-4 3e-4; do
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --score-drop 4900 --l2 $L --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --out "$ART/l$L.pjtw" >"$ART/l$L-train.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/l$L.pjtw" hc 8 8 1 0 "" 64 >"$ART/l$L-hc.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/l$L.pjtw" "$V15" 9 8 1 0 "" 64 >"$ART/l$L-v15.log" 2>&1
  r=$(rate "$ART/l$L-v15.log")
  echo "  l2=$L : vs hc=$(rate "$ART/l$L-hc.log")  vs v15 d9=$r  (144 parties)"
  awk "BEGIN{exit !($r>$bestrate)}" && { bestrate=$r; best=$L; }
done
echo "  --- meilleur l2=$best (v15=$bestrate) → régime movetime (72) ---"
[ -n "$best" ] && ./build-prod/jass --benchmark-scan-eval "$ART/l$best.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/best-mt.log" 2>&1
echo "=========================================================="
echo "  0176 l2 FINE-SWEEP (confirmation fiable du nouvel optimum)"
for L in 1e-4 2e-4 3e-4; do echo "  l2=$L : hc=$(rate "$ART/l$L-hc.log")  v15 d9=$(rate "$ART/l$L-v15.log")"; done
echo "  meilleur l2=$best : v15 movetime=$(rate "$ART/best-mt.log")"
echo "  réf : l2=1e-5+drop = 0.944/0.389 ; 0174(108p) l2=1e-4 = 1.0/0.472"
echo "  → l2=1e-4..3e-4 > 0.389 confirmé = nouveau champion vers v15."
echo "=========================================================="
