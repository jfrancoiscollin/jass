#!/usr/bin/env bash
# id: cpx62-0336-search-combo-confirm
# description: Confirmation PROPRE du combo focalisé issu de 0334/0335 : multicut(facile) + razor(d4) =
# les porteurs du gain ; probcut/iid droppés. Moins de candidats (4) sur 16 cœurs → quasi pas de contention
# CPU (le bruit qui faisait osciller 0333/0334), plus de parties (90). A=candidat vs B=défaut, temps fixe.
# But : CHIFFRER le gain net et figer le combo avant de le baker (0337 → vs Scan).
# expected_duration: ~2-2.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0336-search-combo-confirm/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent ($DATA)"; exit 4; }
MT=700; PAIRS=5; DCAP=30   # 90 parties/candidat, 4 candidats → 4 procs sur 16 cœurs (contention minimale)

preflight_build 1
preflight_train 240000 1
preflight_note "confirm 4 candidats × 90 parties @ ${MT}ms (4 procs/16 cœurs)" 130
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

MC="multicut_min_depth=6,multicut_moves=8,multicut_cuts=2"
# A=candidat vs B=défaut. A-rate>0.5 = gain net à temps fixe.
CANDS=(
  "mc_only|$MC"
  "mc_razor|$MC,razor_max_depth=4"
  "mc_razor_ct|$MC,razor_max_depth=4,use_conthist=1"
  "mc_razor_pc|$MC,razor_max_depth=4,probcut_min_depth=6,probcut_margin=250"
)
echo "=== confirmation ${#CANDS[@]} candidats × $((PAIRS*18)) parties @ ${MT}ms ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   cpx62-0336 — CONFIRMATION combo recherche focalisé (propre, ${MT}ms, $((PAIRS*18)) parties)"
echo "----------------------------------------------------------"
printf "  %-13s %-58s %s\n" "candidat" "spec" "A-rate (>0.5 = MIEUX)"
best=""; bestr="0"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-13s %-58s %s\n" "$name" "$spec" "${rate:-NA}"
  if [ -n "$rate" ] && awk "BEGIN{exit !($rate>$bestr)}"; then bestr="$rate"; best="$name → $spec"; fi
done
echo "----------------------------------------------------------"
echo "   MEILLEUR : ${best:-aucun} @ ${bestr}"
echo "   razor aide ? = mc_razor vs mc_only. conthist/probcut ? = _ct/_pc vs mc_razor."
echo "   Suite 0337 : baker le gagnant dans search_params.hpp + valider vs Scan à temps égal."
echo "=========================================================="
