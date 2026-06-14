#!/usr/bin/env bash
# id: ccx33-0256-eg-pieces-sweep
# description: SWEEP DU SEUIL du régime recherche finale (eg_no_nmp). 0255 a donné +29.4 Elo
# pour eg_no_nmp au seuil popcount<=12 ; on cherche le MEILLEUR seuil. On compare 3 seuils
# (8 / 12 / 16) vs le régime OFF EXPLICITE (eg_pieces=0) — NB le défaut a changé (eg_no_nmp@12
# est désormais ON), donc le baseline doit être eg_pieces=0 explicite, pas "". improving=1
# reste actif des deux côtés (défaut), donc on isole bien l'effet du SEUIL au-dessus d'improving.
# Plus de parties que 0255 (pairs=35 ≈ 630/comparaison) pour mieux résoudre. Éval men-only 0227
# (locale CCX33, comme 0255). CCX33 = box réservée aux tests de search.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0256-eg-pieces-sweep/artefacts.src"; mkdir -p "$ART"
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
[ -n "$EVAL" ] || { echo "ABORT: éval men-only 0227 introuvable (box recyclée ?)"; exit 6; }
echo "EVAL (men-only) = $EVAL"

MT=200; PAIRS=35     # mt0.2s ; ~630 parties/comparaison (plus que 0255 pour mieux résoudre)
OFF="eg_pieces=0"    # baseline = régime finale OFF EXPLICITE (le défaut est maintenant ON@12)

run_ab() {  # TAG  <A spec>
  local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[$OFF] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "$OFF" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}

run_ab thr8  "eg_pieces=8,eg_no_nmp=1"   &
run_ab thr12 "eg_pieces=12,eg_no_nmp=1"  &
run_ab thr16 "eg_pieces=16,eg_no_nmp=1"  &
wait

echo; echo "=========================================================="
echo "   ccx33-0256 — SWEEP SEUIL eg_pieces (eg_no_nmp) : A=seuil ON vs B=régime OFF"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison  (improving=ON des 2 côtés)"
echo "----------------------------------------------------------"
BEST_TAG=""; BEST_ELO="-999"
for tag in thr8 thr12 thr16; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line" | grep -oE 'A=[0-9]+' | cut -d= -f2)
  L=$(echo "$line" | grep -oE 'B=[0-9]+' | cut -d= -f2)
  D=$(echo "$line" | grep -oE 'Draws=[0-9]+' | cut -d= -f2)
  if [ -z "${W:-}" ]; then echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; fi
  E=$(python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" 2>/dev/null | grep -oE 'elo=[-+0-9.]+' | head -1 | cut -d= -f2)
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
  if awk -v e="${E:-0}" -v b="$BEST_ELO" 'BEGIN{exit !(e>b)}'; then BEST_ELO="$E"; BEST_TAG="$tag"; fi
done
echo "----------------------------------------------------------"
echo "  MEILLEUR seuil (Elo brut) : $BEST_TAG  (elo=$BEST_ELO)"
echo "  Si les 3 seuils sont ~équivalents (différences << bruit) → le seuil n'est pas critique,"
echo "  garder 12. Si un seuil domine nettement → l'adopter comme défaut (search_params.hpp)."
echo "=========================================================="
