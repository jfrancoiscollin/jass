#!/usr/bin/env bash
# id: 0194-logistic-wdl-scan-objective
# description: RECETTE SCAN — étape 1 : la VRAIE objectif de Scan = régression
# LOGISTIQUE sur les ISSUES de partie (WDL), pas des moindres carrés. Nos essais
# WDL antérieurs (0177) étaient en moindres carrés et se sont effondrés. Ici, le
# vrai logistique (cross-entropy, score = logit) sur le master 1.4M (issues de
# parties). Sweep l2. Bench vs v15 (d9 + movetime) + hc.
#
#   réf champion (distill score Scan-d10) : v15 d9≈0.47  movetime≈0.38.
#   logistique-WDL ≥ ça = l'objectif Scan marche sur nos données → fondation de
#     la boucle self-play itérée. < ça = master WDL trop bruité → besoin du
#     self-play (étape 2).
#
# expected_duration: ~1.5-2 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0194-logistic-wdl-scan-objective/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
for L in 1e-5 1e-4 1e-3; do
  echo; echo "=== logistic-WDL, l2=$L ==="
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
    --loss logistic --l2 $L --max-iter 200 --scale 1000 --out "$ART/log$L.pjtw" \
    >"$ART/train-$L.log" 2>&1
  grep -E "loss=LOGISTIC|train_loss" "$ART/train-$L.log" | sed 's/^/    /'
  [ -f "$ART/log$L.pjtw" ] || { echo "  ABORT train $L"; continue; }
  ./build-prod/jass --benchmark-scan-eval "$ART/log$L.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/l$L-v15d9.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/log$L.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/l$L-v15mt.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/log$L.pjtw" hc    8  6 1 0   "" 64 >"$ART/l$L-hc.log"    2>&1
  echo "  l2=$L : v15 d9=$(rate "$ART/l$L-v15d9.log")  mt=$(rate "$ART/l$L-v15mt.log")  hc=$(rate "$ART/l$L-hc.log")"
done

echo; echo "=========================================================="
echo "        0194 LOGISTIC-WDL (objectif Scan) — VERDICT"
for L in 1e-5 1e-4 1e-3; do
  echo "  l2=$L : v15 d9=$(rate "$ART/l$L-v15d9.log")  mt=$(rate "$ART/l$L-v15mt.log")  hc=$(rate "$ART/l$L-hc.log")"
done
echo "  réf champion (distill score) : v15 d9≈0.47  mt≈0.38"
echo "  → ≥ ça = l'objectif logistique de Scan marche → fondation self-play itéré."
echo "  → << ça = master WDL trop bruité → passer au self-play (étape 2)."
echo "=========================================================="
