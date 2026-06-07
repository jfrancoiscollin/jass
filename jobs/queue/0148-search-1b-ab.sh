#!/usr/bin/env bash
# id: 0148-search-1b-ab
# description: A/B des 4 briques search 1b (continuation history, improving,
# IID, multi-cut), CHACUNE isolée vs le défaut (toutes off), pour décider
# lesquelles flipper en défaut. SCOPE ALLÉGÉ (v1 tournait ~8h) : v15 seul,
# 2 paires, depth 9 + movetime 200 court (la passe v3 reviendra une fois
# l'éval réparée). Une brique « gated, neutre » ne devient défaut que validée.
#
# Convention : --benchmark-search-params A=<spec brique> B=<défaut "">.
#   A score rate > 0.5  → la brique aide (ELO > 0) → candidate au flip défaut.
#   ≈ 0.5               → neutre → laisser gated, SPSA décidera par éval.
#   < 0.5               → nuit → laisser off.
#
# expected_duration: ~30-50 min (scope allégé).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0148-search-1b-ab"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
V3=$(ls -t /root/jass/jobs/results/0147-scan-eval-full/artefacts.src/scan_eval_v3.pjtw 2>/dev/null | head -1)
echo "v15 : $V15"; echo "v3  : ${V3:-<absent, on saute la passe v3>}"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || {
    echo "TESTS FAIL"; tail -20 "$ART/tests.log"; exit 6; }

declare -A SPECS=(
    [conthist]="use_conthist=1"
    [improving]="use_improving=1"
    [iid]="iid_min_depth=4,iid_reduction=2"
    [multicut]="multicut_min_depth=5,multicut_reduction=4,multicut_moves=6,multicut_cuts=3"
    [all]="use_conthist=1,use_improving=1,iid_min_depth=4,multicut_min_depth=5"
)

rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
elo () { python3 -c "import math,sys
r=float(sys.argv[1])
print('n/a' if not(0<r<1) else f'{-400*math.log10(1/r-1):+.0f}')" "$1" 2>/dev/null || echo n/a; }

run_passe () {  # $1=label net  $2=net path  $3=depth  $4=movetime
    local label="$1" net="$2" d="$3" mt="$4"
    echo; echo "########## PASSE $label  (depth=$d movetime=$mt) ##########"
    for name in conthist improving iid multicut all; do
        local log="$ART/${label}-${name}-d${d}-mt${mt}.log"
        ./build-prod/jass --benchmark-search-params "$net" "${SPECS[$name]}" "" \
            "$d" 2 1 "$mt" 2>&1 | tee "$log" >/dev/null
        local r; r=$(rate_sp "$log")
        printf "  %-10s A=[%s]  rate=%s  ELO %s\n" "$name" "${SPECS[$name]}" "${r:-?}" "$(elo "${r:-0.5}")"
    done
}

run_passe "v15" "$V15" 9 0
run_passe "v15" "$V15" 64 200
# NB: scope ALLÉGÉ (2 paires, pas de movetime 300, pas de passe v3) — la v1
# « 6 paires × movetime × v15+v3 » tournait ~8h. On A/B les briques sur v15
# (vraie éval) en depth + un movetime court ; la passe v3 reviendra une fois
# l'éval réparée (le prior v3 actuel perd 0/90, A/B dessus = peu décisif).

echo; echo "=========================================================="
echo "  0148 — VERDICT 1b : flipper en défaut les briques rate>0.53"
echo "  de façon consistante (v15 + v3, depth + movetime)."
echo "=========================================================="
