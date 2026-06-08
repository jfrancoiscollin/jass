#!/usr/bin/env bash
# id: 0166-geometry-investigation
# description: INVESTIGATION POINT PAR POINT #2 — géométrie. Pourquoi ajouter 8
# blocs diagonaux (v4 32 → v5 40) a fait chuter le jeu (0.72 → 0.44 vs hc) ?
# Anormal : avec L2, des features en plus prennent de petits poids. Hypothèse
# n°1 = régularisation trop faible pour le plus gros modèle. On teste les DEUX
# géométries (générateur paramétrable) avec un SWEEP L2 {1e-5, 1e-4, 1e-3} sur
# le 1.4M PROPRE, benchs vs hc sur 108 parties (±0.048).
#
# Lecture : si le meilleur l2 de v5 rattrape v4 (~0.72) → c'était la régul (et
# la richesse est récupérable). Si v5 reste sous v4 à tout l2 → les blocs
# diagonaux nuisent vraiment (redondance/conditionnement).
# Référence fiable (0165) : v4 l2=1e-5 = 0.72 vs hc.
#
# expected_duration: ~2-3 h (2 builds + 6 trains + 6 benchs).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0166-geometry-investigation"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo "ABORT: 1.4M propre (0141) absent"; exit 3; }
echo "1.4M propre : $CLEAN"
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
FEAT=""   # dumpé une fois (extras 106 inchangés entre v4/v5)

run_variant () {  # $1 = v4|v5
    local V="$1"
    echo; echo "##################### VARIANT $V #####################"
    python3 pattern_jass/tools/gen_patterns.py --variant "$V" --emit 2>&1 | tail -1
    rm -rf build-prod
    cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/$V-cmake.log" 2>&1
    cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/$V-build.log" 2>&1 || { echo "BUILD FAIL $V"; tail -20 "$ART/$V-build.log"; return; }
    ./build-prod/jass_tests > "$ART/$V-tests.log" 2>&1 && echo "  tests OK" || { echo "TESTS FAIL $V"; return; }
    local NP; NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import importlib,patterns;importlib.reload(patterns);print(patterns.NUM_PATTERNS)")
    echo "  NUM_PATTERNS=$NP"
    # dump features une seule fois (identique entre variants)
    if [ -z "$FEAT" ]; then FEAT="$ART/clean.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1; fi
    for l2 in 1e-5 1e-4 1e-3; do
        local m="$ART/$V-l2$l2.pjtw"
        python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
            --target score --score-clip 5000 --l2 "$l2" --max-iter 200 --scale 1000 \
            --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$m" > "$ART/$V-l2$l2-train.log" 2>&1
        local vm; vm=$(grep -oE "mse=[0-9.]+" "$ART/$V-l2$l2-train.log" | head -1)
        if [ -f "$m" ]; then
            ./build-prod/jass --benchmark-scan-eval "$m" hc 8 6 1 0 "" 64 > "$ART/$V-l2$l2-vs-hc.log" 2>&1
            echo "  $V l2=$l2 : vs hc=$(anyrate "$ART/$V-l2$l2-vs-hc.log")  ($vm)"
        else
            echo "  $V l2=$l2 : ÉCHEC train"
        fi
        rm -f "$m"
    done
}

run_variant v4
run_variant v5

echo; echo "=========================================================="
echo "        0166 GÉOMÉTRIE v4(32) vs v5(40) × sweep l2 — VERDICT"
echo "  (vs hc, 108 parties ±0.048 ; réf fiable 0165 : v4 l2=1e-5 = 0.72)"
for V in v4 v5; do
  for l2 in 1e-5 1e-4 1e-3; do
    echo "  $V l2=$l2 : $(anyrate "$ART/$V-l2$l2-vs-hc.log")"
  done
done
echo "  → meilleur v5 ≈ meilleur v4 = régul (richesse récupérable, re-tuner l2)."
echo "  → meilleur v5 < v4 partout = les blocs diagonaux nuisent vraiment."
echo "=========================================================="
