#!/usr/bin/env bash
# id: 0171-geometry-retest-with-drop
# description: TOURNANT — re-tester la GÉOMÉTRIE avec le score-drop. 0166 avait
# condamné v5 (40 patterns, blocs diagonaux) car 0.53 < 0.72 — MAIS sur baseline
# EMPOISONNÉ (scores extrêmes). 0170 : le filtre transforme v4 (0.72→0.944 vs hc,
# 0.11→0.389 vs v15). Donc on re-teste v4 vs v5 SUR BASE SAINE (score-drop 4900),
# benchs FIABLES vs hc (180) ET v15 (144).
#
# Nouveau baseline (0170) : v4+drop/1.4M = 0.944 vs hc, 0.389 vs v15.
# Lecture : v5+drop > v4+drop = la richesse diagonale était masquée par le poison
# → on rouvre tout l'axe géométrie/extras vers v15. Sinon v4 reste le set.
#
# expected_duration: ~2-2.5 h (2 builds + 2 distills + 4 benchs).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0171-geometry-retest-with-drop"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: 1.4M (0141) absent"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
FEAT=""

run_variant () {  # $1 = v4|v5
    local V="$1"
    echo; echo "##################### VARIANT $V (score-drop 4900) #####################"
    python3 pattern_jass/tools/gen_patterns.py --variant "$V" --emit 2>&1 | tail -1
    rm -rf build-prod
    cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/$V-cmake.log" 2>&1
    cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/$V-build.log" 2>&1 || { echo "BUILD FAIL $V"; tail -20 "$ART/$V-build.log"; return; }
    ./build-prod/jass_tests > "$ART/$V-tests.log" 2>&1 && echo "  tests OK" || { echo "TESTS FAIL $V"; return; }
    echo "  NUM_PATTERNS=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import importlib,patterns;importlib.reload(patterns);print(patterns.NUM_PATTERNS)")"
    if [ -z "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --score-drop 4900 --l2 1e-5 --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$V.pjtw" > "$ART/$V-train.log" 2>&1
    grep -E "score-drop|val   :" "$ART/$V-train.log" | sed 's/^/    /'
    [ -f "$ART/$V.pjtw" ] || { echo "  $V : train ÉCHEC"; return; }
    ./build-prod/jass --benchmark-scan-eval "$ART/$V.pjtw" hc 8 10 1 0 "" 64 > "$ART/$V-vs-hc.log" 2>&1
    ./build-prod/jass --benchmark-scan-eval "$ART/$V.pjtw" "$V15" 9 8 1 0 "" 64 > "$ART/$V-vs-v15.log" 2>&1
    echo "  $V+drop : vs hc=$(anyrate "$ART/$V-vs-hc.log")  vs v15 d9=$(anyrate "$ART/$V-vs-v15.log")"
    rm -f "$ART/$V.pjtw"
}

run_variant v4
run_variant v5

echo; echo "=========================================================="
echo "        0171 GÉOMÉTRIE RE-TEST (avec score-drop) — VERDICT"
echo "  (vs hc 180 ±0.037 ; vs v15 d9 144)"
echo "  v4+drop : vs hc=$(anyrate "$ART/v4-vs-hc.log")  vs v15=$(anyrate "$ART/v4-vs-v15.log")"
echo "  v5+drop : vs hc=$(anyrate "$ART/v5-vs-hc.log")  vs v15=$(anyrate "$ART/v5-vs-v15.log")"
echo "  (rappel 0170 : v4+drop = 0.944 / 0.389)"
echo "  → v5 > v4 = la richesse diagonale paie sur base saine → rouvrir géométrie+extras."
echo "  → v5 ≤ v4 = les blocs nuisent vraiment, v4 reste le set."
echo "=========================================================="
