#!/usr/bin/env bash
# id: ccx33-0259-eg-pieces-sweep2
# description: SWEEP SEUIL eg_pieces (eg_no_nmp) — EXTENSION vers le haut. 0256 a donné une
# tendance MONOTONE croissante : thr8=+17, thr12=+31, thr16=+47 (vs régime OFF), pic NON atteint.
# On étend : seuils 20 / 28 / 36 vs OFF explicite (eg_pieces=0), improving=ON des deux côtés.
# Combiné à 0256 → courbe complète 8/12/16/20/28/36. thr36 ≈ NMP quasi totalement OFF (départ
# = 40 pièces) : si ça continue de monter jusqu'à 36, conclusion = NMP est NET-NÉGATIF en jass
# (le désactiver globalement / monter nmp_min_pieces). Sinon on lit le pic et on l'adopte.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0259-eg-pieces-sweep2/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval men-only 0227 introuvable"; exit 6; }
echo "EVAL (men-only) = $EVAL"

MT=200; PAIRS=30; OFF="eg_pieces=0"
run_ab() { local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[$OFF] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "$OFF" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}
run_ab thr20 "eg_pieces=20,eg_no_nmp=1" &
run_ab thr28 "eg_pieces=28,eg_no_nmp=1" &
run_ab thr36 "eg_pieces=36,eg_no_nmp=1" &
wait

echo; echo "=========================================================="
echo "   ccx33-0259 — SWEEP SEUIL eg_pieces (EXTENSION 20/28/36) vs régime OFF"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison  (improving=ON)"
echo "   rappel 0256 : thr8=+17  thr12=+31  thr16=+47 (monotone croissant)"
echo "----------------------------------------------------------"
for tag in thr20 thr28 thr36; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line"|grep -oE 'A=[0-9]+'|cut -d= -f2); L=$(echo "$line"|grep -oE 'B=[0-9]+'|cut -d= -f2); D=$(echo "$line"|grep -oE 'Draws=[0-9]+'|cut -d= -f2)
  [ -z "${W:-}" ] && { echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; }
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  Lire la courbe 8/12/16/20/28/36 : pic = seuil optimal à adopter (search_params.hpp)."
echo "  Si monotone jusqu'à 36 → NMP net-négatif en jass : désactiver globalement / nmp_min_pieces↑."
echo "=========================================================="
