#!/usr/bin/env bash
# id: 0157-eval-throughput-profile
# description: MESURE de débit (knps) + depth en recherche RÉELLE, pour décider
# l'éval incrémentale des patterns. Le micro-bench (--bench-eval) est faussé
# (position constante → hoisting), et un net à zéros donne un arbre dégénéré ;
# il faut les VRAIS nets et --depth-at-movetime (positions variables, budget
# fixe → knps = throughput réel quand la recherche use le budget).
#
# Compare, à 300ms : 32-patterns recompute (0154-A) | handcrafted | NNUE v15
# (qui, lui, A un accumulateur incrémental). Lectures :
#   - knps(32-pat) vs knps(hc) = surcoût des patterns+extras (recompute).
#   - knps(v15) = cible « incrémental rapide » (l'accumulateur NNUE).
#   - depth atteinte = impact réel sur la force de recherche.
# → dimensionne le gain attendu d'un accumulateur pattern avant de le coder.
#
# expected_duration: ~5-10 min.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0157-eval-throughput-profile"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

A=$(ls -t /root/jass/jobs/results/0154-richer-patterns-distill/artefacts.src/A.pjtw 2>/dev/null | head -1)
[ -n "$A" ] && [ -f "$A" ] || { echo "ABORT: net 32-patterns (0154-A) manquant"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "32-pat (0154-A) : $A"; echo "v15 : $V15"

echo; echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }

for mt in 300 1000; do
  echo; echo "########## movetime = ${mt}ms ##########"
  echo "--- 32-patterns vs handcrafted ---"
  ./build-prod/jass --depth-at-movetime "$A"   hc  "$mt" 2>&1 | tee "$ART/pat-vs-hc-${mt}.log"   | grep -E "depth avg|knps|reaches"
  echo "--- v15 (NNUE incrémental) vs handcrafted ---"
  ./build-prod/jass --depth-at-movetime "$V15" hc  "$mt" 2>&1 | tee "$ART/v15-vs-hc-${mt}.log"   | grep -E "depth avg|knps|reaches"
  echo "--- 32-patterns vs v15 ---"
  ./build-prod/jass --depth-at-movetime "$A"   "$V15" "$mt" 2>&1 | tee "$ART/pat-vs-v15-${mt}.log" | grep -E "depth avg|knps|reaches"
done

echo; echo "=========================================================="
echo "        0157 DÉBIT D'ÉVAL — LECTURE"
echo "  Comparer knps : 32-pat (recompute) vs hc vs v15 (incrémental)."
echo "  Grand écart 32-pat << v15 en knps = l'accumulateur pattern vaut le coup."
echo "  Petit écart = l'éval n'est pas le goulot → autre levier."
echo "=========================================================="
