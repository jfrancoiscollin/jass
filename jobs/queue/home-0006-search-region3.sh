#!/usr/bin/env bash
# id: home-0006-search-region3
# description: PC perso (WSL) dans la flotte recherche. Sweep 100% self-contained : build SIMPLE (pas d'egdb),
# éval HANDCRAFTED (pas de data/torch), self-play A/B à TEMPS FIXE. 3e région orthogonale à 0334 (membres) /
# 0335 (marges) : late-move-pruning, aspiration, singular extensions, history. A=candidat vs B=défaut ;
# A-rate>0.5 = gain net. Les gagnants seront re-validés avec l'éval pattern sur cpx62.
# expected_duration: ~1.5-2 h (sweep parallèle à temps fixe)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/home-0006-search-region3/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MT=600; PAIRS=3; DCAP=30

preflight_build 1
preflight_note "sweep région-3 ~8 candidats @ ${MT}ms, ${PAIRS}pairs (×$NCPU parallèle)" 110
preflight_check

echo "=== build jass SIMPLE (Release, pas d'egdb — éval handcrafted) ==="
B=build-hc; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1 || { echo "CMAKE FAIL"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

# A=candidat vs B=défaut, éval handcrafted (hc). A-rate>0.5 = MIEUX à temps fixe.
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
echo "=== sweep région-3 ${#CANDS[@]} (hc, parallèle ×$NCPU) ==="
for c in "${CANDS[@]}"; do
  name="${c%%|*}"; spec="${c##*|}"
  ( "$JASS" --benchmark-search-params hc "$spec" "" "$DCAP" "$PAIRS" 1 "$MT" \
       >"$ART/c-$name.log" 2>&1 ) &
done
wait

echo; echo "=========================================================="
echo "   home-0006 — sweep recherche région-3 (hc, temps fixe ${MT}ms)"
echo "----------------------------------------------------------"
printf "  %-14s %s\n" "candidat" "A-rate (>0.5 = MIEUX)"
for c in "${CANDS[@]}"; do
  name="${c%%|*}"
  rate=$(grep -E 'A score rate' "$ART/c-$name.log" | grep -oE '[0-9.]+' | head -1)
  printf "  %-14s %s\n" "$name" "${rate:-NA}"
done
echo "----------------------------------------------------------"
echo "   >0.5 → candidat à re-valider avec l'éval pattern sur cpx62 (région orthogonale à 0334/0335)."
echo "=========================================================="
