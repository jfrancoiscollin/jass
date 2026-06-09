#!/usr/bin/env bash
# id: 0186-geometry-v6-diagonal-dense
# description: ROUTE SCAN / piste 1 — GÉOMÉTRIE DIAGONALE DENSE. Les dames est un
# jeu diagonal mais nos 32 patterns v4 sont des bandes VERTICALES (désalignées).
# v6 remplace par un set aligné sur les axes de jeu : toutes les bandes ET blocs
# diagonaux/anti-diagonaux distincts (+ qq horiz/carré pour couvrir) = 40 patterns
# denses sur les diagonales. Teste si aligner+densifier (le mécanisme de Scan)
# bat les bandes verticales.
#
#   v4 (réf, 0176) : v15 d9=0.472  movetime=0.382.
#   v6 distillé (même recette) vs v15 d9 + movetime + hc.
#
# NB : .paused — ne se lance QUE si déqueué (route Scan, si le FM 0184 ne convertit
# pas). gen_patterns --emit ne modifie que des fichiers SOURCE (le runner ne
# committe que jobs/results/ — pas de pollution de main).
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0186-geometry-v6-diagonal-dense/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }

echo "=== émettre la géométrie v6 (diagonale dense) ==="
python3 pattern_jass/tools/gen_patterns.py --variant v6 --emit 2>&1 | tail -2
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp

echo; echo "=== build prod + tests (v6) ==="
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo; echo "=== distill champion sur géométrie v6 ==="
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v6.pjtw" 2>&1 | grep -E "val   :|wrote"
[ -f "$ART/v6.pjtw" ] || { echo "ABORT train"; exit 7; }
./build-prod/jass --benchmark-scan-eval "$ART/v6.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/v15d9.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v6.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/v15mt.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v6.pjtw" hc    8  6 1 0   "" 64 >"$ART/hc.log"    2>&1

echo; echo "=========================================================="
echo "        0186 GÉOMÉTRIE v6 DIAGONALE DENSE — VERDICT"
echo "  v6 (40 patterns diag) : v15 d9=$(rate "$ART/v15d9.log")  mt=$(rate "$ART/v15mt.log")  hc=$(rate "$ART/hc.log")"
echo "  v4 réf (32 vert)      : v15 d9=0.472  mt=0.382  hc≈1.0"
echo "  → v6 mt > 0.382 = l'alignement diagonal + densité aide (route Scan vivante)."
echo "  → ≈/< = la géométrie diagonale dense seule ne suffit pas."
echo "=========================================================="
