#!/usr/bin/env bash
# id: home-0008-rfp-confirm
# description: PC perso — confirme le lead RFP de home-0007 (rfp_aggr=0.639) PAR-DESSUS le combo baké
# (défaut = multicut+razor maintenant), avec plus de parties (72) et des variantes de marge/profondeur RFP.
# Self-contained (hc). A=combo+rfp-variante vs B="" (=combo baké). >0.5 = RFP ajoute au combo.
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-110}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/home-0008-rfp-confirm/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MT=500; PAIRS=4; DCAP=30

preflight_build 1
preflight_note "sweep RFP 6 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU)" 70
preflight_check

echo "=== build jass SIMPLE (Release, hc ; defaults = combo baké) ==="
B=build-hc; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1 || { echo "CMAKE FAIL"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

# A = combo baké + variante RFP ; B = "" (= combo baké). >0.5 = RFP ajoute.
CANDS=(
  "rfp7_70|rfp_max_depth=7,rfp_margin=70"
  "rfp7_50|rfp_max_depth=7,rfp_margin=50"
  "rfp6_70|rfp_max_depth=6,rfp_margin=70"
  "rfp8_80|rfp_max_depth=8,rfp_margin=80"
  "rfp7_90|rfp_max_depth=7,rfp_margin=90"
  "rfp_razlow|rfp_max_depth=7,rfp_margin=70,razor_margin=120"
)
echo "=== sweep RFP ${#CANDS[@]} (hc, vs combo baké, parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params hc "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   home-0008 — RFP par-dessus le combo baké (hc, temps fixe ${MT}ms, $((PAIRS*18)) parties)"
echo "----------------------------------------------------------"
printf "  %-12s %s\n" "variante" "A-rate vs combo-baké (>0.5 = RFP ajoute)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-12s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.5 net → valider la meilleure variante RFP sur l'éval pattern (cpx62/ccx33) puis baker."
echo "=========================================================="
