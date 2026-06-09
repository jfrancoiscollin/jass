#!/usr/bin/env bash
# id: 0187-geometry-v7-regions
# description: ROUTE SCAN / piste 2 — PATTERNS SPÉCIALISÉS PAR RÉGION. Au lieu de
# paver uniformément, on dépense les fenêtres là où l'information est dense : les
# 2 bandes de promotion (rangées 0-2 et 7-9), les longues diagonales centrales,
# les bords gauche/droite (pions de bord faibles) et le centre. Placement
# draughts-spécifique. v7 = set LEAN (15 patterns) mais bien placés — teste si
# "moins mais mieux placé" généralise mieux que "32 génériques".
#
#   v4 (réf, 0176) : v15 d9=0.472  movetime=0.382.
#   v7 distillé (même recette) vs v15 d9 + movetime + hc.
#
# NB : .paused — ne se lance QUE si déqueué (route Scan).
# expected_duration: ~1.5-2.5 h (15 patterns = design plus léger).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0187-geometry-v7-regions/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }

echo "=== émettre la géométrie v7 (régions stratégiques) ==="
python3 pattern_jass/tools/gen_patterns.py --variant v7 --emit 2>&1 | tail -2
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp

echo; echo "=== build prod + tests (v7) ==="
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

echo; echo "=== distill champion sur géométrie v7 ==="
FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v7.pjtw" 2>&1 | grep -E "val   :|wrote"
[ -f "$ART/v7.pjtw" ] || { echo "ABORT train"; exit 7; }
./build-prod/jass --benchmark-scan-eval "$ART/v7.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/v15d9.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v7.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/v15mt.log" 2>&1
./build-prod/jass --benchmark-scan-eval "$ART/v7.pjtw" hc    8  6 1 0   "" 64 >"$ART/hc.log"    2>&1

echo; echo "=========================================================="
echo "        0187 GÉOMÉTRIE v7 RÉGIONS — VERDICT"
echo "  v7 (15 patterns placés) : v15 d9=$(rate "$ART/v15d9.log")  mt=$(rate "$ART/v15mt.log")  hc=$(rate "$ART/hc.log")"
echo "  v4 réf (32 génériques)  : v15 d9=0.472  mt=0.382  hc≈1.0"
echo "  → v7 ≥ v4 = 'moins mais mieux placé' gagne → placement = levier."
echo "  → < v4 = trop peu de fenêtres ; densifier les régions clés."
echo "=========================================================="
