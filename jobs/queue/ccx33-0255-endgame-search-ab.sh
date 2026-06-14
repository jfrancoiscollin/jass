#!/usr/bin/env bash
# id: ccx33-0255-endgame-search-ab
# description: TIER SEARCH-FINALE — A/B du « régime de recherche finale » (popcount-gated).
# 0252 a montré que la finale est SEARCH-BOUND (la recherche profonde rattrape une éval
# faible) ET tactiquement tranchante à faible branching : les réductions/élagages agressifs
# (NMP zugzwang, LMP/LMR sur des coups calmes mais gagnants uniques) y risquent de jeter LA
# bonne ligne pour peu de nœuds économisés. On a ajouté un régime gated (eg_pieces<=N →
# désactive NMP/LMP/LMR au choix) ; ici on MESURE, mécanisme par mécanisme + combiné, vs
# baseline, sur la championne men-only locale (0227). --benchmark-search-params = MÊME éval
# des deux côtés, au movetime (budget honnête). 4 comparaisons EN PARALLÈLE, SPRT par compare.
#   eg_no_nmp / eg_no_lmp / eg_no_lmr / les trois   (seuil eg_pieces=12 = zone finale tranchante)
# CCX33 = box réservée aux tests de search (la densification tourne sur CPX62).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0255-endgame-search-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

# --- build MEN-ONLY jass (défaut) pour charger l'éval men-only 0227 ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- éval men-only locale (0227 gen8, repli 0231) ---
EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval men-only 0227 introuvable (box recyclée ?)"; exit 6; }
echo "EVAL (men-only) = $EVAL"

MT=200; PAIRS=25; EGP=12     # mt0.2s ; ~450 parties/comparaison ; régime finale popcount<=12

# run_ab TAG "<A spec>" : A vs baseline B="" , movetime, depth cap 64
run_ab() {
  local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[baseline] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}

run_ab nmp "eg_pieces=$EGP,eg_no_nmp=1"                          &
run_ab lmp "eg_pieces=$EGP,eg_no_lmp=1"                          &
run_ab lmr "eg_pieces=$EGP,eg_no_lmr=1"                          &
run_ab all "eg_pieces=$EGP,eg_no_nmp=1,eg_no_lmp=1,eg_no_lmr=1"  &
wait

echo; echo "=========================================================="
echo "   ccx33-0255 — RÉGIME RECHERCHE FINALE (popcount<=$EGP) : A=régime ON vs B=baseline"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison"
echo "----------------------------------------------------------"
for tag in nmp lmp lmr all; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line" | grep -oE 'A=[0-9]+' | cut -d= -f2)
  L=$(echo "$line" | grep -oE 'B=[0-9]+' | cut -d= -f2)
  D=$(echo "$line" | grep -oE 'Draws=[0-9]+' | cut -d= -f2)
  if [ -z "${W:-}" ]; then echo "  [$tag] PAS DE RÉSULTAT — voir ab-$tag.log"; tail -3 "$ART/ab-$tag.log"; continue; fi
  echo "  [eg_no_$tag]  A(ON)=$W  B(OFF)=$L  Draws=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  ACCEPT H1 (>=5 Elo) → activer ce régime finale par défaut (search_params.hpp) + déployer."
echo "  Lire les 3 mécanismes ISOLÉS : si seul eg_no_nmp gagne (cheap, zugzwang) → ne garder que lui ;"
echo "  si eg_no_lmr/lmp perdent (trop lent → moins de profondeur, contre-productif vu search-bound) → off."
echo "  Suivi possible : balayer le seuil eg_pieces (8/12/14) une fois le bon mécanisme isolé."
echo "=========================================================="
