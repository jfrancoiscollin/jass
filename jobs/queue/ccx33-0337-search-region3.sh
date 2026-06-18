#!/usr/bin/env bash
# id: ccx33-0337-search-region3
# description: 3e région de params recherche (rapatriée du PC perso offline) AVEC l'éval pattern (cohérent
# 0334/0335/0336) : late-move-pruning, aspiration, singular, history. Orthogonal au combo multicut+razor.
# A=candidat vs B=défaut, self-play à TEMPS FIXE. Gagnants combinés au combo focalisé puis validés vs Scan.
# expected_duration: ~1.5-2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0337-search-region3/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent ($DATA)"; exit 4; }
MT=600; PAIRS=4; DCAP=30

preflight_build 1
preflight_train 240000 1
preflight_note "sweep région-3 8 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU)" 110
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

CANDS=(
  "lmp_tight|lmp_d1=3,lmp_d2=6,lmp_d3=10"
  "lmp_loose|lmp_d1=6,lmp_d2=12,lmp_d3=18"
  "asp_tight|aspiration_initial=30"
  "asp_wide|aspiration_initial=80"
  "singular6|singular_min_depth=6"
  "history_big|history_max=32768"
  "history_small|history_max=8192"
  "lmp_asp|lmp_d1=3,lmp_d2=6,lmp_d3=10,aspiration_initial=40"
)
echo "=== sweep région-3 ${#CANDS[@]} (éval pattern, parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   ccx33-0337 — sweep recherche région-3 (éval pattern, temps fixe ${MT}ms, $((PAIRS*18)) parties)"
echo "----------------------------------------------------------"
printf "  %-14s %s\n" "candidat" "A-rate (>0.5 = MIEUX)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-14s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.5 → combiner au combo multicut+razor (0336) puis valider vs Scan."
echo "=========================================================="
