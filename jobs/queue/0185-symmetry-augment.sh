#!/usr/bin/env bash
# id: 0185-symmetry-augment
# description: ROUTE SCAN #1 — partage de poids par SYMÉTRIE (data-augmentation).
# Nos 32 tables de patterns sont affamées car non partagées (vs ~4 sous-tables
# chez Scan). Le SEUL symétrie géométrique exploitable du damier (cases sombres)
# est la rotation 180° + échange des couleurs (le miroir gauche-droite envoie
# sombre→clair sur un plateau pair×pair). On DOUBLE les données avec cette
# symétrie (stm-POV score/wdl PRÉSERVÉS, vérifié 100%) : ça force les tables à
# être cohérentes sous la symétrie = effet de partage / meilleure généralisation.
#
#   control : champion v3 sur 1.4M.
#   augmenté: champion v3 sur 2.8M (1.4M + image symétrique).
#   v15 d9 + movetime. Augmenté > control = la symétrie aide (route Scan vivante).
#
# NB : .paused — ne se lance QUE si on le déqueue (au cas où le FM 0184 échoue).
# expected_duration: ~2-3 h (distill sur 2.8M).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0185-symmetry-augment/artefacts.src"; mkdir -p "$ART"
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

echo; echo "=== augmente le master par symétrie (1.4M → 2.8M) ==="
AUG="$ART/aug.jnnw"; ./build-prod/jass --symmetry-augment "$CLEAN" "$AUG" 2>&1 | tail -1

bench(){ ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 9  6 1 0   "" 64 >"$ART/$1-v15d9.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" "$V15" 64 4 1 300 "" 64 >"$ART/$1-v15mt.log" 2>&1
         ./build-prod/jass --benchmark-scan-eval "$ART/$1.pjtw" hc    8  6 1 0   "" 64 >"$ART/$1-hc.log"    2>&1
         echo "  $1 : v15 d9=$(rate "$ART/$1-v15d9.log")  mt=$(rate "$ART/$1-v15mt.log")  hc=$(rate "$ART/$1-hc.log")"; }
distill(){ local tag="$1" data="$2"
  ./build-prod/jass --dump-eval-features "$data" "$ART/$tag.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$data" --scan-eval --eval-features-file "$ART/$tag.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" 2>&1 | grep -E "val   :|wrote"; }

echo; echo "=== control : champion sur 1.4M ==="
distill ctrl "$CLEAN"  ; bench ctrl
echo; echo "=== augmenté : champion sur 2.8M (symétrie) ==="
distill aug  "$AUG"    ; bench aug

echo; echo "=========================================================="
echo "        0185 SYMÉTRIE (route Scan) — VERDICT"
echo "  control 1.4M : v15 d9=$(rate "$ART/ctrl-v15d9.log")  mt=$(rate "$ART/ctrl-v15mt.log")  hc=$(rate "$ART/ctrl-hc.log")"
echo "  augmenté 2.8M: v15 d9=$(rate "$ART/aug-v15d9.log")  mt=$(rate "$ART/aug-v15mt.log")  hc=$(rate "$ART/aug-hc.log")"
echo "  → augmenté > control (surtout mt) = la cohérence par symétrie généralise"
echo "    mieux → la route Scan (partage/géométrie) est un levier réel."
echo "  → ≈ = la symétrie ne suffit pas ; passer au partage de poids DUR ou à"
echo "    la géométrie dense (plus de fenêtres)."
echo "=========================================================="
