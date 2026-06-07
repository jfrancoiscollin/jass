#!/usr/bin/env bash
# id: 0150-speed-depth-lever
# description: QUANTIFIE + EXPLOITE le levier vitesse→profondeur de la v3.
# Trois pistes, dans l'ordre :
#   (1) MESURER : profondeur atteinte par v3 vs v15 à temps égal (movetime)
#       — l'écart de plies EST la taille du levier.
#   (2) TT : la profondeur monte-t-elle avec la taille de TT ? et le taux de
#       victoire vs v15 ? (une petite TT plafonne la profondeur réalisée).
#   (3) TIME-MGMT : le facteur de saut d'itération (réglé pour le régime NNUE
#       ~depth 15-20) bride-t-il la v3 en haute profondeur (~30+) ? A/B de
#       tm_next_iter_pct vs défaut, en movetime.
#
# Le « fast side » est la v3 de 0147 si présente, sinon le handcrafted (hc)
# qui est aussi rapide → le job tourne même sans 0147.
#
# expected_duration: ~1-2 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0150-speed-depth-lever"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
FAST=$(ls -t /root/jass/jobs/results/0147-scan-eval-full/artefacts.src/scan_eval_v3.pjtw 2>/dev/null | head -1)
[ -n "$FAST" ] && [ -f "$FAST" ] || { FAST="hc"; echo "note: prior v3 (0147) absent → fast side = handcrafted"; }
echo "v15 (slow) : $V15"; echo "fast side  : $FAST"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || {
    echo "TESTS FAIL"; tail -20 "$ART/tests.log"; exit 6; }

echo; echo "########## (1) MESURE : profondeur à temps égal ##########"
for mt in 100 300 1000; do
    echo "--- movetime ${mt}ms (tt=64MB) ---"
    ./build-prod/jass --depth-at-movetime "$FAST" "$V15" "$mt" 64 2>&1 | tee "$ART/depth-mt${mt}.log"
done

echo; echo "########## (2a) TT : profondeur vs taille de TT (movetime 300ms) ##########"
for tt in 8 16 64 256; do
    echo "--- tt=${tt}MB ---"
    ./build-prod/jass --depth-at-movetime "$FAST" "$V15" 300 "$tt" 2>&1 | tee "$ART/depth-tt${tt}.log"
done

rate_se () { grep -oE 'SCAN_EVAL score rate vs NNUE: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

if [ "$FAST" != "hc" ]; then
    echo; echo "########## (2b) TT : taux vs v15 à tt=16 vs tt=128 (movetime 300) ##########"
    for tt in 16 128; do
        ./build-prod/jass --benchmark-scan-eval "$FAST" "$V15" 64 5 1 300 "use_conthist=1,iid_min_depth=4" "$tt" \
            2>&1 | tee "$ART/rate-tt${tt}.log"
        echo "  tt=${tt}MB → rate=$(rate_se "$ART/rate-tt${tt}.log")"
    done
fi

echo; echo "########## (3) TIME-MGMT : A/B du saut d'itération (movetime 300) ##########"
# A = variante haute-profondeur (projection plus permissive → tente l'itération
#     de plus), B = défaut (200%). Net = fast side (la v3 / hc).
for spec in "tm_next_iter_pct=140" "tm_next_iter_pct=300" "tm_min_depth=8"; do
    log="$ART/tm-$(echo "$spec" | tr '=,' '__').log"
    ./build-prod/jass --benchmark-search-params "$FAST" "$spec" "" 64 5 1 300 2>&1 | tee "$log" >/dev/null
    echo "  A=[$spec] vs défaut → rate=$(rate_sp "$log")"
done

echo; echo "=========================================================="
echo "        0150 LEVIER VITESSE→PROFONDEUR — LECTURE"
echo "=========================================================="
echo "  (1) Δplies (fast − v15) à 300ms : $(grep -h 'reaches' "$ART/depth-mt300.log" | grep -oE '[-0-9.]+ plies' | head -1)"
echo "  (2) profondeur fast à tt=8 vs 256 :"
grep -h 'A ' "$ART/depth-tt8.log"  -A1 | grep depth | sed 's/^/      tt8 :/'
grep -h 'A ' "$ART/depth-tt256.log" -A1 | grep depth | sed 's/^/      tt256:/'
echo "  → si profondeur monte avec TT : agrandir la TF en jeu profond."
echo "  → si une variante tm_* bat le défaut : régler le time-mgmt haute prof."
echo "=========================================================="
