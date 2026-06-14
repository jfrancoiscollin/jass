#!/usr/bin/env bash
# id: cpx62-0253-search-features-ab
# description: TIER-1 VITESSE — active + mesure les features de recherche DÉJÀ CODÉES mais
# OFF par défaut (continuation-history `use_conthist`, improving-heuristic `use_improving`).
# Ce sont des réducteurs de NŒUDS (meilleur ordonnancement → plus de profondeur au même
# temps = vitesse effective + force), gratuits à part le risque qu'au réglages LMR/LMP
# actuels (tunés en régime OFF) ils soient neutres/négatifs. On le tranche par A/B :
# --benchmark-search-params joue MÊME éval des deux côtés, spec A vs spec B, au MOVETIME
# (le budget honnête : la feature gagne en allant plus profond dans le même temps). Trois
# comparaisons EN PARALLÈLE (box idle), verdict SPRT par comparaison.
#   conthist seul / improving seul / les deux   — chacun vs baseline (rien).
# On teste sur la CHAMPIONNE king-aware (0241 gen8) pour que le tuning soit pertinent.
# NB : le tuning recherche SPÉCIFIQUE FINALE (LMR/LMP/NMP par popcount<8) demande du CODE
# (params uniformes aujourd'hui) → c'est un job séparé ; ici on prend la partie déjà codée.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0253-search-features-ab/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

# --- build KING-AWARE jass (pour charger l'éval king-aware de 0241) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: build pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- éval championne king-aware (0241 gen8, repli gen7) ---
EVAL=""
for cand in /root/jass/jobs/results/cpx62-0241-kingloop-scaled/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/cpx62-0241-kingloop-scaled/artefacts.src/gen7.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval king-aware 0241 introuvable (box recyclée ?)"; exit 6; }
echo "EVAL (king-aware) = $EVAL"

MT=200      # per-move milliseconds (the harness takes movetime_ms ; 0.2s realistic & bounded)
PAIRS=25    # total games = pairs*2*9 openings = 450 games per comparison

# run_ab TAG  "<A spec>"  : A vs baseline B="" , at movetime MT, dump to its own log
run_ab() {
  local tag="$1" aspec="$2"
  echo "=== [$tag] A=[$aspec] vs B=[baseline] : mt${MT}ms pairs=$PAIRS ==="
  # depth arg = 64 = a high CAP so movetime is the binding budget (the ID loop is
  # `depth <= max_depth` → a 0 cap would skip the search entirely).
  "$JASS" --benchmark-search-params "$EVAL" "$aspec" "" 64 "$PAIRS" 1 "$MT" \
      >"$ART/ab-$tag.log" 2>&1
}

# three comparisons IN PARALLEL (single-thread each → independent cores on the idle box)
run_ab conthist  "use_conthist=1"                  &
run_ab improving "use_improving=1"                 &
run_ab both      "use_conthist=1,use_improving=1"  &
wait

echo; echo "=========================================================="
echo "   cpx62-0253 — FEATURES RECHERCHE (Tier-1) : A=feature ON vs B=baseline OFF"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison"
echo "----------------------------------------------------------"
for tag in conthist improving both; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line" | grep -oE 'A=[0-9]+' | cut -d= -f2)
  L=$(echo "$line" | grep -oE 'B=[0-9]+' | cut -d= -f2)
  D=$(echo "$line" | grep -oE 'Draws=[0-9]+' | cut -d= -f2)
  if [ -z "${W:-}" ]; then echo "  [$tag] PAS DE RÉSULTAT — voir ab-$tag.log"; tail -3 "$ART/ab-$tag.log"; continue; fi
  echo "  [$tag]  A(ON)=$W  B(OFF)=$L  Draws=$D"
  # Elo de A vs B + IC Wilson + verdict SPRT (la feature vaut-elle >= 5 Elo ?)
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  ACCEPT H1 (>=5 Elo) → activer la feature par défaut (search_params.hpp) + déployer."
echo "  ACCEPT H0 / négatif → laisser OFF (ou re-tuner LMR/LMP AVEC la feature = SPSA, job suivant)."
echo "  CONTINUE → étendre le nombre de parties (verdict pas encore significatif)."
echo "=========================================================="
