#!/usr/bin/env bash
# id: cpx62-0334-search-combo-refine
# description: Raffine le gagnant de 0333 (combo des prunings depth-buying = 0.639 à temps fixe). (1) ablations
# (le combo est-il MEILLEUR sans conthist, qui seul nuit ? quels membres portent le gain ?), avec PLUS de
# parties (90, moins de bruit). (2) confirme à temps PLUS LONG (1500ms : le bénéfice de profondeur doit
# grandir). Tout en parallèle. A=candidat vs B=défaut ; A-rate>0.5 = gain net à temps fixe.
# expected_duration: ~2 h (sweep + confirmation longue, parallèle ×NCPU)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0334-search-combo-refine/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent ($DATA)"; exit 4; }
MT=600; PAIRS=5; DCAP=30; MT_LONG=1500; PAIRS_LONG=2

preflight_build 1
preflight_train 240000 1
preflight_note "sweep ablations 90 parties + confirmation 1500ms (×$NCPU parallèle)" 130
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "=== build jass FULL Scan-alignée ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
echo "=== train éval représentative ==="
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }

PC="probcut_min_depth=5"; RZ="razor_max_depth=3"; MC="multicut_min_depth=6"; II="iid_min_depth=6"; CT="use_conthist=1"
# ablations @ 600ms (90 parties)
CANDS=(
  "combo5_90|$PC,$RZ,$MC,$II,$CT|$MT|$PAIRS"
  "combo_noct|$PC,$RZ,$MC,$II|$MT|$PAIRS"
  "no_probcut|$RZ,$MC,$II|$MT|$PAIRS"
  "no_razor|$PC,$MC,$II|$MT|$PAIRS"
  "no_multicut|$PC,$RZ,$II|$MT|$PAIRS"
  "no_iid|$PC,$RZ,$MC|$MT|$PAIRS"
  "aggr|probcut_min_depth=4,razor_max_depth=4,multicut_min_depth=5,iid_min_depth=5|$MT|$PAIRS"
  "noct_plus_rfp|$PC,$RZ,$MC,$II,rfp_max_depth=6,rfp_margin=80|$MT|$PAIRS"
  # confirmation à temps long (1500ms, 36 parties) des deux principaux
  "combo5_LONG|$PC,$RZ,$MC,$II,$CT|$MT_LONG|$PAIRS_LONG"
  "combo_noct_LONG|$PC,$RZ,$MC,$II|$MT_LONG|$PAIRS_LONG"
)
echo "=== sweep ${#CANDS[@]} (parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  IFS='|' read -r name spec mt pairs <<<"$c"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$pairs" 1 "$mt" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   cpx62-0334 — RAFFINEMENT combo recherche (ablations + temps long)"
echo "----------------------------------------------------------"
printf "  %-16s %-7s %-6s %s\n" "candidat" "mt(ms)" "games" "A-rate (>0.5 = MIEUX)"
for c in "${CANDS[@]}"; do
  IFS='|' read -r name spec mt pairs <<<"$c"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  games=$(grep -oE 'total [0-9]+' "$ART/c-$name.log" | grep -oE '[0-9]+' | head -1)
  printf "  %-16s %-7s %-6s %s\n" "$name" "$mt" "${games:-?}" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   Cherche : le sous-ensemble qui MAXIMISE A-rate (no_X bas → X porte le gain)."
echo "   LONG > 600ms → le bénéfice de profondeur grandit avec le temps (attendu)."
echo "   Suite : geler le meilleur combo + valider vs Scan à profondeur égale / temps compensé."
echo "=========================================================="
