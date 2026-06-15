#!/usr/bin/env bash
# id: ccx33-0269-history-aging
# description: SEARCH — A/B de l'history-aging (gravity). L'history s'accumulait sans bornes
# (h += depth²) → les vieux cutoffs dominent l'ordonnancement des coups calmes. Nouveau param
# gated `history_max` : règle gravity h += b - h*b/history_max (cap ~history_max + décroissance
# des grosses valeurs anciennes). history_max=0 = legacy (défaut). On sweep le cap vs baseline.
# Standard ~+5-15 Elo. A/B isolés, SPRT. Éval men-only 0227, baseline = NMP-off actuel.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0269-history-aging/artefacts.src"; mkdir -p "$ART"
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
[ -n "$EVAL" ] || { echo "ABORT: éval 0227 introuvable"; exit 6; }
echo "EVAL = $EVAL"
MT=200; PAIRS=25
run_ab() { local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[baseline, history_max=0] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}
run_ab h8k  "history_max=8192"   &
run_ab h16k "history_max=16384"  &
run_ab h32k "history_max=32768"  &
wait
echo; echo "=========================================================="
echo "   ccx33-0269 — HISTORY AGING (gravity) : A=history_max vs B=legacy(0)"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison"
echo "----------------------------------------------------------"
for tag in h8k h16k h32k; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line"|grep -oE 'A=[0-9]+'|cut -d= -f2); L=$(echo "$line"|grep -oE 'B=[0-9]+'|cut -d= -f2); D=$(echo "$line"|grep -oE 'Draws=[0-9]+'|cut -d= -f2)
  [ -z "${W:-}" ] && { echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; }
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  Un cap >0 → l'adopter par défaut (search_params.hpp history_max). Tous ~0 → l'history"
echo "     non-bornée ne nuit pas ici (peu de coups calmes en dames → ordonnancement déjà bon)."
echo "=========================================================="
