#!/usr/bin/env bash
# id: ccx33-0342-lmp-rfp-confirm
# description: Confirme PROPREMENT (self-play, sensible) le candidat lmp5+rfp7 (0340 = 0.625 sur pattern, mais
# 72 parties/2σ et contredit le hc). Plus de parties (90), peu de candidats (faible contention), éval pattern.
# A=combo+tweak vs B=combo baké. Décide si on bake lmp5+rfp7 (en parallèle de la mesure vs Scan 0341).
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0342-lmp-rfp-confirm/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
MT=700; PAIRS=5; DCAP=30   # 90 parties, 4 candidats → 4 procs/8 cœurs (faible contention)

preflight_build 1
preflight_train 240000 1
preflight_note "confirm 4 candidats × 90 parties @ ${MT}ms" 120
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

CANDS=(
  "rfp7|rfp_max_depth=7,rfp_margin=70"
  "lmp5|lmp_max_depth=5"
  "lmp5_rfp7|lmp_max_depth=5,rfp_max_depth=7,rfp_margin=70"
  "lmp5_rfp7_h|lmp_max_depth=5,rfp_max_depth=7,rfp_margin=70,lmr_hist_div=3000"
)
echo "=== confirm ${#CANDS[@]} × $((PAIRS*18)) parties @ ${MT}ms (vs combo baké) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   ccx33-0342 — CONFIRMATION lmp5+rfp7 (pattern, $((PAIRS*18)) parties, faible contention)"
echo "----------------------------------------------------------"
printf "  %-12s %s\n" "candidat" "A-rate vs combo-baké (>0.5 = ajoute)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-12s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.55 net (confirme 0340) → baker lmp5+rfp7. ≈0.5 → c'était du bruit, combo final = multicut+razor."
echo "=========================================================="
