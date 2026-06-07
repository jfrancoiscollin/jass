#!/usr/bin/env bash
# id: 0158-scan-accumulator-speedup
# description: Mesure le gain de l'accumulateur pattern (PR #243) sur le VRAI net
# 32-patterns (0154-A), et re-confirme la correction A/B (ON vs OFF = résultats
# identiques avec un net non-trivial). JASS_NO_SCAN_ACC=1 force le recompute.
#   - depth-at-movetime 0154-A vs hc, ON puis OFF → knps(ON) > knps(OFF) = gain.
#   - benchmark-scan-eval 0154-A vs hc, ON vs OFF → MÊME score = correction.
# Baseline recompute (0157) : ~1549 knps @300ms, depth ~16.8.
#
# expected_duration: ~10-15 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0158-scan-accumulator-speedup"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

A=$(ls -t /root/jass/jobs/results/0154-richer-patterns-distill/artefacts.src/A.pjtw 2>/dev/null | head -1)
[ -n "$A" ] && [ -f "$A" ] || { echo "ABORT: net 32-patterns (0154-A) manquant"; exit 3; }
echo "net 32-patterns : $A"

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }

knps () { grep -E "knps" "$1" | head -1 | grep -oE "knps~[0-9.]+" | grep -oE "[0-9.]+"; }
depth () { grep -E "depth avg" "$1" | head -1 | grep -oE "depth avg=[0-9.]+" | grep -oE "[0-9.]+"; }
rate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

echo; echo "########## VITESSE : depth-at-movetime 0154-A vs hc ##########"
for mt in 300 1000; do
  ./build-prod/jass                 --depth-at-movetime "$A" hc "$mt" > "$ART/on-${mt}.log"  2>&1
  JASS_NO_SCAN_ACC=1 ./build-prod/jass --depth-at-movetime "$A" hc "$mt" > "$ART/off-${mt}.log" 2>&1
  echo "  ${mt}ms : ON  knps=$(knps "$ART/on-${mt}.log")  depth=$(depth "$ART/on-${mt}.log")"
  echo "          OFF knps=$(knps "$ART/off-${mt}.log") depth=$(depth "$ART/off-${mt}.log")"
done

echo; echo "########## CORRECTION : 0154-A vs hc, ON vs OFF (doit être identique) ##########"
./build-prod/jass                 --benchmark-scan-eval "$A" hc 9 3 1 0 "" 64 > "$ART/corr-on.log"  2>&1
JASS_NO_SCAN_ACC=1 ./build-prod/jass --benchmark-scan-eval "$A" hc 9 3 1 0 "" 64 > "$ART/corr-off.log" 2>&1
echo "  ON  rate=$(rate "$ART/corr-on.log")   OFF rate=$(rate "$ART/corr-off.log")"

echo; echo "=========================================================="
echo "        0158 ACCUMULATEUR PATTERN — VERDICT"
for mt in 300 1000; do
  echo "  @${mt}ms : knps ON=$(knps "$ART/on-${mt}.log") vs OFF=$(knps "$ART/off-${mt}.log")  | depth ON=$(depth "$ART/on-${mt}.log") vs OFF=$(depth "$ART/off-${mt}.log")"
done
echo "  correction : ON rate=$(rate "$ART/corr-on.log") == OFF rate=$(rate "$ART/corr-off.log") ?"
echo "  → knps(ON) > knps(OFF) = gain accumulateur ; rates égaux = correct."
echo "=========================================================="
