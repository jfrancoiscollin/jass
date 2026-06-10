#!/usr/bin/env bash
# id: 0188-speed-conversion-diagnostic
# description: DIAGNOSTIC DÉCISIF — pourquoi la connaissance (d9 monte) ne se
# convertit PAS au movetime (plafond ~0.38) ? Deux causes : (A) éval trop lente
# (on n'atteint pas la profondeur), (B) la connaissance plafonne quelle que soit
# la profondeur. On tranche sur v4 (champion) ET v6 (diagonale, meilleur d9=0.556) :
#
#   (1) ÉCHELLE rate(depth) FIABLE : vs v15 à depth {7,9,11,13}, 144 parties/point.
#       MONTE avec la profondeur → conversion OK → borné VITESSE (piste A : optimiser).
#       PLAFONNE/descend → plafond de capacité (piste B : tête non-linéaire).
#   (2) VITESSE : depth-at-movetime + knps de v4, v6 vs v15. Quantifie le coût.
#
# expected_duration: ~3-4 h (échelle profonde × 2 évals).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0188-speed-conversion-diagnostic/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
rate(){ grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null|grep -oE '[0-9.]+$'|head -1; }

# $1 = tag (v4|v6) ; suppose le binaire build-prod déjà construit pour la bonne géométrie
distill_and_probe(){
  local tag="$1"
  echo "  -- distill $tag --"
  ./build-prod/jass --dump-eval-features "$CLEAN" "$ART/$tag.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/$tag.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$tag.pjtw" >"$ART/$tag-train.log" 2>&1
  [ -f "$ART/$tag.pjtw" ] || { echo "  ABORT distill $tag"; return; }
  echo "  -- échelle rate(depth) $tag (144 parties/point) --"
  for D in 7 9 11 13; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" "$V15" $D 8 1 0 "" 64 >"$ART/$tag-d$D.log" 2>&1
    echo "    $tag depth=$D : $(rate "$ART/$tag-d$D.log")"
  done
  echo "  -- vitesse $tag (depth-at-movetime) --"
  ./build-prod/jass --depth-at-movetime "$ART/$tag.pjtw" "$V15" 300  64 2>&1 | grep -iE "depth avg" >"$ART/$tag-dam300.log"; cat "$ART/$tag-dam300.log" | sed 's/^/    300ms  /'
  ./build-prod/jass --depth-at-movetime "$ART/$tag.pjtw" "$V15" 1000 64 2>&1 | grep -iE "depth avg" >"$ART/$tag-dam1000.log"; cat "$ART/$tag-dam1000.log" | sed 's/^/    1000ms /'
}

echo "=== v4 (champion, 32 bandes verticales) ==="
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake4.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build4.log" 2>&1 || { echo BUILD4 FAIL; tail -20 "$ART/build4.log"; exit 5; }
distill_and_probe v4

echo; echo "=== v6 (diagonale dense, 40 patterns) ==="
python3 pattern_jass/tools/gen_patterns.py --variant v6 --emit >"$ART/emit6.log" 2>&1
grep -m1 "NUM_PATTERNS  =" pattern_jass/src/pattern.hpp
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake6.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build6.log" 2>&1 || { echo BUILD6 FAIL; tail -20 "$ART/build6.log"; exit 5; }
distill_and_probe v6

echo; echo "=========================================================="
echo "        0188 DIAGNOSTIC VITESSE/CONVERSION — VERDICT"
echo "  rate(depth) vs v15 (144 parties) :"
for t in v4 v6; do
  printf "    %s :" "$t"; for D in 7 9 11 13; do printf "  d%s=%s" "$D" "$(rate "$ART/$t-d$D.log")"; done; echo
done
echo "  vitesse (depth atteinte @ movetime, A=pattern B=v15) :"
echo "    v4 300ms : $(cat "$ART/v4-dam300.log" 2>/dev/null | paste -sd' | ')"
echo "    v6 300ms : $(cat "$ART/v6-dam300.log" 2>/dev/null | paste -sd' | ')"
echo "  → rate qui MONTE avec depth = borné VITESSE (piste A : optimiser l'éval)."
echo "  → rate qui PLAFONNE = plafond de capacité (piste B : tête non-linéaire)."
echo "=========================================================="
