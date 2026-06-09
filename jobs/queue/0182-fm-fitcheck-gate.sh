#!/usr/bin/env bash
# id: 0182-fm-fitcheck-gate
# description: GATE FM (Python pur, pas de C++). AVANT de construire une éval FM
# en C++ (vraie charge : terme d'interaction + éval + accumulateur), on teste si
# des interactions par paires réduisent VRAIMENT l'erreur held-out au-delà du
# modèle linéaire. Sur le master propre (score, drop4900), sweep du rang k.
#
#   réduction nette du val_mse (>~5-10%) = signal d'interaction → construire FM.
#   ≈0% = pas d'interaction exploitable → ne PAS construire FM (capacité ≠ levier).
#
# Probe local (60K) : +1.5%. Ici : 400K, hash 8192, k∈{4,8,16}, 150 iters.
# expected_duration: ~1-1.5 h (Python pur).
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0182-fm-fitcheck-gate/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

FEAT="$ART/feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1

echo; echo "=== FM fit-check : sweep du rang k (400K, hash 8192, drop4900) ==="
for K in 4 8 16; do
  echo "--- rank $K ---"
  python3 pattern_jass/tools/fm_fitcheck.py --data "$CLEAN" --eval-features-file "$FEAT" \
    --subsample 400000 --rank $K --hash 8192 --l2 1e-4 --l2-fm 1e-3 --max-iter 150 \
    2>&1 | tee "$ART/k$K.log" | grep -E "rows|val_mse|VERDICT|linear"
done

echo; echo "=========================================================="
echo "        0182 GATE FM — VERDICT (réduction du val_mse)"
for K in 4 8 16; do
  L=$(grep -oE 'linear      val_mse = [0-9.]+' "$ART/k$K.log" | grep -oE '[0-9.]+$' | head -1)
  F=$(grep -oE 'linear \+ FM val_mse = [0-9.]+' "$ART/k$K.log" | grep -oE '[0-9.]+$' | head -1)
  R=$(grep -oE '\([+-][0-9.]+% vs linear\)' "$ART/k$K.log" | head -1)
  echo "  rank=$K : linear=$L  FM=$F  $R"
done
echo "  → meilleur k avec réduction >~5-10% = construire le FM C++."
echo "  → tous ≈0-2% = capacité d'interaction n'est PAS le levier → pas FM."
echo "  (caveat : single-phase + stage-feature ; une partie du gain peut"
echo "   recouvrir le phase-split déjà présent en prod — interpréter prudemment.)"
echo "=========================================================="
