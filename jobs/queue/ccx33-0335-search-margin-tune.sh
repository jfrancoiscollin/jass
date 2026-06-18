#!/usr/bin/env bash
# id: ccx33-0335-search-margin-tune
# description: Axe ORTHOGONAL à 0334 (qui fait les ablations). Ici on TUNE les marges/seuils des prunings
# depth-buying autour du combo de base (probcut5+razor3+multicut6+iid6) : A = base + UN réglage modifié,
# B = base. A-rate>0.5 = le réglage améliore le combo. Jugé à TEMPS FIXE (méthodo permanente). En parallèle
# de cpx62-0334 → on couvre on/off ET marges en même temps. Le meilleur combo+marges ira ensuite vs Scan.
# expected_duration: ~1.5 h (sweep parallèle à temps fixe)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-160}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0335-search-margin-tune/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw  # committé
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent ($DATA)"; exit 4; }
MT=600; PAIRS=4; DCAP=30
BASE="probcut_min_depth=5,razor_max_depth=3,multicut_min_depth=6,iid_min_depth=6"

preflight_build 1
preflight_train 240000 1
preflight_note "sweep marges ~8 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU parallèle)" 100
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

# A = base + UN tweak (vs B = base). A-rate>0.5 = tweak améliore le combo.
CANDS=(
  "pc_margin80|$BASE,probcut_margin=80"
  "pc_margin250|$BASE,probcut_margin=250"
  "pc_depth4|$BASE,probcut_min_depth=4"
  "pc_red5|$BASE,probcut_reduction=5"
  "razor_d4|$BASE,razor_max_depth=4"
  "mc_easy|$BASE,multicut_moves=8,multicut_cuts=2"
  "mc_depth5|$BASE,multicut_min_depth=5"
  "iid_depth5|$BASE,iid_min_depth=5"
)
echo "=== sweep marges ${#CANDS[@]} (base=$BASE) parallèle ×$NCPU ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params "$ART/eval.pjtw" "$spec" "$BASE" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   ccx33-0335 — TUNING marges du combo recherche (vs base, temps fixe ${MT}ms)"
echo "   base = $BASE"
echo "----------------------------------------------------------"
printf "  %-14s %s\n" "tweak" "A-rate vs base (>0.5 = AMÉLIORE)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-14s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.5 → adopter le tweak. Combiner les gagnants de 0334 (membres) + 0335 (marges) → combo final."
echo "=========================================================="
