#!/usr/bin/env bash
# id: ccx33-0344-hist-malus
# description: Test de FORCE du history-malus (codé 2026-06-18) PAR-DESSUS le combo baké, éval pattern, 90
# parties, faible contention. A=combo+hist_malus=V vs B="" (=combo baké). >0.55 net → baker. Le node-count
# à depth fixe est trompeur (ordering↔LMR/LMP) → seul l'A/B de force décide. Lève l'eval-sensitivity (hc vs pattern).
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0344-hist-malus/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
MT=700; PAIRS=5; DCAP=30

preflight_build 1
preflight_train 240000 1
preflight_note "sweep hist_malus 4 candidats × 90 parties @ ${MT}ms" 120
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
echo "=== train éval ==="
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }

CANDS=( "hm50|hist_malus=50" "hm100|hist_malus=100" "hm150|hist_malus=150" "hm200|hist_malus=200" )
echo "=== sweep hist_malus (vs combo baké, ${PAIRS}pairs) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" >"$ART/c-$name.log" 2>&1 ) &
done
wait
echo; echo "=========================================================="
echo "   ccx33-0344 — history-malus (pattern, $((PAIRS*18)) parties, vs combo baké)"
echo "----------------------------------------------------------"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-8s %s\n" "$name" "${rate:-NA}"
done
echo "   >0.55 net → baker hist_malus=V. ≈0.5 → ordering déjà optimal, ne pas baker."
echo "=========================================================="
