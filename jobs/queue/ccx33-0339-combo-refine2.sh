#!/usr/bin/env bash
# id: ccx33-0339-combo-refine2
# description: Raffinement PAR-DESSUS le combo baké (multicut+razor est maintenant le DÉFAUT). A=défaut+tweak
# vs B="" (=combo baké) : A-rate>0.5 = le tweak améliore encore le combo. On gratte multicut_reduction,
# razor_margin, cuts/moves/min_depth, razor_max_depth, + history_big (le ~1σ de la région-3). Temps fixe.
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0339-combo-refine2/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
MT=600; PAIRS=4; DCAP=30

preflight_build 1
preflight_train 240000 1
preflight_note "sweep raffinement 8 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU)" 110
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "=== build jass FULL Scan-alignée (defaults = combo baké) ==="
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

# A = défaut(combo baké) + tweak ; B = "" (= combo baké). A-rate>0.5 = améliore encore.
CANDS=(
  "mc_red3|multicut_reduction=3"
  "mc_red5|multicut_reduction=5"
  "razor_m120|razor_margin=120"
  "razor_m300|razor_margin=300"
  "mc_cuts1|multicut_cuts=1"
  "mc_moves10|multicut_moves=10"
  "razor_d5|razor_max_depth=5"
  "history_big|history_max=32768"
)
echo "=== sweep raffinement ${#CANDS[@]} (vs combo baké) parallèle ×$NCPU ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   ccx33-0339 — raffinement PAR-DESSUS le combo baké (temps fixe ${MT}ms, $((PAIRS*18)) parties)"
echo "----------------------------------------------------------"
printf "  %-13s %s\n" "tweak" "A-rate vs combo-baké (>0.5 = encore mieux)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-13s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.5 net → ajouter au combo baké (nouveau bake). Sinon → combo actuel déjà bien calé."
echo "=========================================================="
