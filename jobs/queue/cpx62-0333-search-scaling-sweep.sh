#!/usr/bin/env bash
# id: cpx62-0333-search-scaling-sweep
# description: LEVIER RECHERCHE (le dominant, 0332 : jass branche 2.0/ply vs Scan 1.28). Les prunings qui
# APLATISSENT l'arbre sans l'hypothèse zugzwang (interdite → NMP off) sont TOUS OFF par défaut : probcut,
# razor, multicut, iid. Ils ont été calés sous l'ancien benchmark à PROFONDEUR FIXE, qui sous-évalue
# structurellement tout ce qui ACHÈTE de la profondeur. On les rallume et on juge à TEMPS FIXE (self-play
# A=candidat vs B=défaut, movetime 600ms) : un meilleur scaling = plus de profondeur dans le même temps =
# gagne. A-rate > 0.5 → le candidat améliore la force réelle. Candidats en parallèle (×NCPU).
# expected_duration: ~1.5 h (sweep parallèle à temps fixe)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0333-search-scaling-sweep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw  # committé (éval représentative)
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent ($DATA)"; exit 4; }
MT=600; PAIRS=3; DCAP=30   # temps fixe 600ms/coup, 54 parties/candidat, cap profondeur large

preflight_build 1
preflight_train 240000 1
preflight_note "sweep ${PAIRS}pairs × ~9 candidats @ ${MT}ms (×$NCPU parallèle)" 90
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

echo "=== train éval représentative (distrib 0314, Scan-relabel) ==="
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }

# candidats : "nom|spec" — A=spec (candidat) vs B="" (défaut). A-rate>0.5 = candidat MEILLEUR à temps fixe.
CANDS=(
  "probcut5|probcut_min_depth=5"
  "probcut4|probcut_min_depth=4,probcut_margin=100"
  "razor3|razor_max_depth=3"
  "multicut6|multicut_min_depth=6"
  "iid6|iid_min_depth=6"
  "conthist|use_conthist=1"
  "lmr_idx4|lmr_idx_div=4"
  "rfp6|rfp_max_depth=6,rfp_margin=80"
  "combo|probcut_min_depth=5,razor_max_depth=3,multicut_min_depth=6,iid_min_depth=6,use_conthist=1"
)
echo "=== sweep ${#CANDS[@]} candidats @ ${MT}ms, ${PAIRS} pairs (parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   cpx62-0333 — sweep RECHERCHE à TEMPS FIXE (${MT}ms) : candidat vs défaut"
echo "----------------------------------------------------------"
printf "  %-12s %-50s %s\n" "candidat" "spec" "A-rate (>0.5 = MIEUX)"
best=""; bestr="0"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-12s %-50s %s\n" "$name" "$spec" "${rate:-NA}"
  if [ -n "$rate" ] && awk "BEGIN{exit !($rate>$bestr)}"; then bestr="$rate"; best="$name ($spec)"; fi
done
echo "----------------------------------------------------------"
echo "   MEILLEUR : ${best:-aucun} @ rate ${bestr}"
echo "   rate > 0.5 → la technique achète de la profondeur nette → GAIN à temps fixe."
echo "   (suite : combiner les gagnants + valider vs Scan à profondeur égale / temps compensé)"
echo "=========================================================="
