#!/usr/bin/env bash
# id: ccx33-0340-lmp-deepen
# description: Teste à TEMPS FIXE le LMP-deepening (lmp_max_depth, codé ce jour) PAR-DESSUS le combo baké,
# et le STACK avec le lead RFP du PC (home-0007). A=combo+tweak vs B="" (=combo baké). >0.5 = gain net.
# Le test de force (le node-count seul ne suffit pas) : la LMP profonde achète-t-elle de la profondeur utile ?
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0340-lmp-deepen/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
MT=600; PAIRS=4; DCAP=30

preflight_build 1
preflight_train 240000 1
preflight_note "sweep LMP-deepen 6 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU)" 110
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "=== build jass FULL Scan-alignée (defaults = combo baké + LMP paramétrable) ==="
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

# A = combo baké + tweak ; B = "" (= combo baké). >0.5 = améliore.
CANDS=(
  "lmp4|lmp_max_depth=4"
  "lmp5|lmp_max_depth=5"
  "lmp6|lmp_max_depth=6"
  "rfp7|rfp_max_depth=7,rfp_margin=70"
  "lmp5_rfp7|lmp_max_depth=5,rfp_max_depth=7,rfp_margin=70"
  "lmp6_rfp7|lmp_max_depth=6,rfp_max_depth=7,rfp_margin=70"
)
echo "=== sweep ${#CANDS[@]} (vs combo baké, parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   ccx33-0340 — LMP-deepening (+RFP) par-dessus le combo baké (temps fixe ${MT}ms, $((PAIRS*18)) parties)"
echo "----------------------------------------------------------"
printf "  %-12s %s\n" "tweak" "A-rate vs combo-baké (>0.5 = mieux)"
best=""; bestr="0.5"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-12s %s\n" "$name" "${rate:-NA}"
  if [ -n "$rate" ] && awk "BEGIN{exit !($rate>$bestr)}"; then bestr="$rate"; best="$name ($spec)"; fi
done
echo "----------------------------------------------------------"
echo "   MEILLEUR : ${best:-aucun > 0.5} @ ${bestr}"
echo "   net >0.5 → ajouter au bake (LMP-deep et/ou RFP). Sinon → combo actuel déjà optimal."
echo "=========================================================="
