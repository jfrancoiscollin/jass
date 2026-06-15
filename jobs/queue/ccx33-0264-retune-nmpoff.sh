#!/usr/bin/env bash
# id: ccx33-0264-retune-nmpoff
# description: RE-TUNE LMR/LMP/RFP avec NMP OFF (l'arbre de recherche a changé : NMP désactivé
# par défaut depuis 0262, eg_pieces=40). Sans NMP, l'arbre est moins élagué → moins de profondeur
# au même temps → hypothèse : élaguer PLUS ailleurs (LMR/LMP/RFP) récupère de la profondeur. On
# A/B 3 candidats PLUS AGRESSIFS, ISOLÉS (leçon : jamais combiné), vs le baseline NMP-off actuel.
#   lmr : lmr_base=2 (réduit 1 pli de plus les coups tardifs)
#   lmp : lmp_d1=3,d2=6,d3=10 (élague plus tôt les quiets tardifs ; défaut 4/8/14)
#   rfp : rfp_max_depth=7 (static-null pruning jusqu'à depth 7 ; défaut 5)
# Baseline B="" = défauts déployés (NMP off, improving on). Éval men-only 0227. SPRT par candidat.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0264-retune-nmpoff/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
# sanity : confirme que le baseline a bien NMP off (eg_pieces=40 par défaut)
grep -q "eg_pieces  = 40" src/search_params.hpp || echo "WARNING: défaut eg_pieces != 40 (NMP pas off ?)"

EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval men-only 0227 introuvable"; exit 6; }
echo "EVAL (men-only) = $EVAL"

MT=200; PAIRS=25
run_ab() { local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[baseline NMP-off] : mt${MT}ms pairs=$PAIRS ==="
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "" 64 "$PAIRS" 1 "$MT" >"$ART/ab-$tag.log" 2>&1
}
run_ab lmr "lmr_base=2"                    &
run_ab lmp "lmp_d1=3,lmp_d2=6,lmp_d3=10"   &
run_ab rfp "rfp_max_depth=7"               &
wait

echo; echo "=========================================================="
echo "   ccx33-0264 — RE-TUNE LMR/LMP/RFP avec NMP OFF : A=plus agressif vs B=baseline"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison"
echo "----------------------------------------------------------"
for tag in lmr lmp rfp; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line"|grep -oE 'A=[0-9]+'|cut -d= -f2); L=$(echo "$line"|grep -oE 'B=[0-9]+'|cut -d= -f2); D=$(echo "$line"|grep -oE 'Draws=[0-9]+'|cut -d= -f2)
  [ -z "${W:-}" ] && { echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; }
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  Un candidat nettement >0 → l'adopter (search_params.hpp) puis raffiner (sweep du knob)."
echo "  Tous ~0 → le tuning LMR/LMP/RFP est robuste à NMP-off (rien à changer là)."
echo "  Un candidat <0 → trop agressif sans NMP (les coupes manquent des tactiques)."
echo "=========================================================="
