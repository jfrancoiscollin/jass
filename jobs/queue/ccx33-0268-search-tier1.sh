#!/usr/bin/env bash
# id: ccx33-0268-search-tier1
# description: SEARCH TIER-1 (post NMP-off) — tester les pistes restantes alignées sur le thème
# « jass déteste l'élagage agressif » (zugzwang). 0264 a tué LMR/LMP PLUS agressif → on teste
# l'AUTRE sens (MOINS agressif) + le re-tuning du TIME-MANAGEMENT (sans NMP, les itérations
# coûtent plus cher → la projection « skip next iter », tunée en régime NMP-on, est mal calibrée).
# A/B isolés vs baseline NMP-off actuel, SPRT par candidat. Éval men-only 0227.
#   lmr_less : lmr_base=0          (1 pli de réduction en MOINS sur les coups tardifs)
#   lmp_less : lmp 6/12/20         (élague PLUS TARD ; défaut 4/8/14)
#   tm_deep  : tm_next_iter_pct=300 (projette l'itération suivante plus chère → skip MOINS → +profond)
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0268-search-tier1/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
grep -q "eg_pieces  = 40" src/search_params.hpp && echo "baseline = NMP off" || echo "WARNING: NMP pas off"

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
run_ab lmr_less "lmr_base=0"                       &
run_ab lmp_less "lmp_d1=6,lmp_d2=12,lmp_d3=20"     &
run_ab tm_deep  "tm_next_iter_pct=300"            &
wait

echo; echo "=========================================================="
echo "   ccx33-0268 — SEARCH TIER-1 (post NMP-off) : A=candidat vs B=baseline"
echo "   éval=$(basename "$EVAL")  mt=${MT}ms  ~$((PAIRS*18)) parties/comparaison"
echo "----------------------------------------------------------"
for tag in lmr_less lmp_less tm_deep; do
  line=$(grep -E '^Result:' "$ART/ab-$tag.log" | tail -1)
  W=$(echo "$line"|grep -oE 'A=[0-9]+'|cut -d= -f2); L=$(echo "$line"|grep -oE 'B=[0-9]+'|cut -d= -f2); D=$(echo "$line"|grep -oE 'Draws=[0-9]+'|cut -d= -f2)
  [ -z "${W:-}" ] && { echo "  [$tag] PAS DE RÉSULTAT"; tail -3 "$ART/ab-$tag.log"; continue; }
  echo "  [$tag]  A=$W B=$L D=$D"
  python3 tools/sprt_elo.py --wdl "$W" "$D" "$L" --elo0 0 --elo1 5 2>/dev/null | sed 's/^/      /'
done
echo "----------------------------------------------------------"
echo "  Un candidat nettement >0 → l'adopter (search_params.hpp) + raffiner (sweep)."
echo "  Tous ~0/<0 → le tuning actuel est déjà bon (recherche conservative + NMP off suffit) ;"
echo "     reste alors l'éval-vitesse (modeste) ou les bitbases comme prochains leviers."
echo "=========================================================="
