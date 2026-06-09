#!/usr/bin/env bash
# id: 0184-fm-distill-bench
# description: FM EN JEU — distille le champion AVEC le terme FM (PJTW v4) et le
# benche vs le linéaire (v3) au régime qui compte (movetime + d9). 0182 a montré
# du signal d'interaction (+13.9% joint, +6.3% pattern-only sur résidu). Ici, le
# FM playable : v3 (linéaire) vs v4 rank8/rank16, mêmes data/recette.
#
#   v4 > v3 à movetime = les interactions de patterns convertissent en force →
#   FM est le levier. v4 ≈ v3 = le gain held-out ne se joue pas (ou coût vitesse).
#
# Le terme FM réutilise les index de l'accumulateur (32 lookups×k) — coût éval
# faible ; le bench movetime intègre tout surcoût de vitesse.
# expected_duration: ~3-4 h.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0184-fm-distill-bench/artefacts.src"; mkdir -p "$ART"
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
COMMON="--data $CLEAN --scan-eval --eval-features-file $FEAT --target score --score-clip 5000 \
  --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0"
distill(){ # $1=tag  $2..=extra args
  local tag="$1"; shift
  python3 pattern_jass/tools/train.py $COMMON "$@" --out "$ART/$tag.pjtw" 2>&1 \
    | tee "$ART/$tag-train.log" | grep -E "val   :|FM :|wrote"
}
bench(){ # $1=tag
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/$1-v15d9.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/$1-v15mt.log" 2>&1
  ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" hc    8  6 1 0   "" 64 >"$ART/$1-hc.log"    2>&1
  echo "  $1 : v15 d9=$(rate "$ART/$1-v15d9.log")  movetime=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"
}

echo; echo "=== v3 linéaire (control) ==="
distill v3 ; bench v3
echo; echo "=== v4 FM rank 8 ==="
distill v4r8  --fm-rank 8  --fm-hash 8192 --l2-fm 1e-3 ; bench v4r8
echo; echo "=== v4 FM rank 16 ==="
distill v4r16 --fm-rank 16 --fm-hash 8192 --l2-fm 1e-3 ; bench v4r16

# profil vitesse : le FM ralentit-il l'éval ? (profondeur atteinte à movetime)
echo; echo "=== vitesse : depth-at-movetime v3 vs v4r8 vs v15 ==="
./build-prod/jass --depth-at-movetime "$ART/v3.pjtw"   "$V15" 300 64 2>&1 | grep -iE "depth avg" | sed 's/^/  v3   /'
./build-prod/jass --depth-at-movetime "$ART/v4r8.pjtw" "$V15" 300 64 2>&1 | grep -iE "depth avg" | sed 's/^/  v4r8 /'

echo; echo "=========================================================="
echo "        0184 FM EN JEU — VERDICT"
echo "  v3 linéaire : v15 d9=$(rate "$ART/v3-v15d9.log")  mt=$(rate "$ART/v3-v15mt.log")  hc=$(rate "$ART/v3-hc.log")"
echo "  v4 FM r8    : v15 d9=$(rate "$ART/v4r8-v15d9.log")  mt=$(rate "$ART/v4r8-v15mt.log")  hc=$(rate "$ART/v4r8-hc.log")"
echo "  v4 FM r16   : v15 d9=$(rate "$ART/v4r16-v15d9.log")  mt=$(rate "$ART/v4r16-v15mt.log")  hc=$(rate "$ART/v4r16-hc.log")"
echo "  réf champion (0176) : v15 d9=0.472  mt=0.382"
echo "  → v4 mt > v3 mt = les interactions paient au temps réel → FM adopté."
echo "  → v4 mt ≈ v3 mt = gain held-out non converti (ou coût vitesse) → creuser."
echo "=========================================================="
