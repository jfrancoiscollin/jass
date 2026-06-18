#!/usr/bin/env bash
# id: home-0007-search-region4
# description: PC perso — 4e région de params recherche, self-contained (build simple, éval handcrafted, pas
# d'egdb/Scan/torch). Orthogonal à 0336 (multicut+razor) / 0337 (lmp/asp/singular/history) : LMR, RFP, razor
# margin, ext_promotion, PVS (sanity). A=candidat vs B=défaut, temps fixe. Court (≈30-40 min) pour valider
# vite que le PC tourne, tout en produisant un vrai signal.
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/home-0007-search-region4/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MT=500; PAIRS=2; DCAP=30

preflight_build 1
preflight_note "sweep région-4 6 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU)" 45
preflight_check

echo "=== build jass SIMPLE (Release, hc) ==="
B=build-hc; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1 || { echo "CMAKE FAIL"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

CANDS=(
  "lmr_aggr|lmr_idx_div=4"
  "rfp_aggr|rfp_max_depth=7,rfp_margin=70"
  "razor_lowm|razor_max_depth=3,razor_margin=120"
  "ext_promo_off|ext_promotion=0"
  "pvs_off|use_pvs=0"
  "lmr_less|lmr_base=1"
)
echo "=== sweep région-4 ${#CANDS[@]} (hc, parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params hc "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   home-0007 — sweep recherche région-4 (hc, temps fixe ${MT}ms)"
echo "----------------------------------------------------------"
printf "  %-14s %s\n" "candidat" "A-rate (>0.5 = MIEUX)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-14s %s\n" "$name" "${rate:-NA}"
done
echo "   (pvs_off doit donner <0.5 — sanity : PVS est net-positif)"
echo "=========================================================="
