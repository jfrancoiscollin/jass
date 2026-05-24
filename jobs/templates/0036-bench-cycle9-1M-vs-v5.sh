#!/usr/bin/env bash
# id: 0036-bench-cycle9-1M-vs-v5
# description: Head-to-head Cycle 9 (1M) vs v5 (0018). Décision pour
#              poursuivre ou arrêter la lignée Cycle 9 :
#                rate > 0.55 → solid gain, le v5-labelling marche.
#                              On peut envisager Cycle 10 (1M
#                              relabelled par v6).
#                rate ∈ [0.50, 0.55] → marginal. Stagner ne vaut pas
#                                     un autre cycle de €10. Pivoter
#                                     vers archi/encoding.
#                rate < 0.50 → régression. Debug pipeline.
# expected_duration: ~45-90 min sur 4 vCPU CCX23.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0036-bench-cycle9-1M-vs-v5"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

CYCLE9=$(ls -t /root/jass/jobs/results/0035-train-cycle9-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(    ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -n "$CYCLE9" ] && [ -f "$CYCLE9" ] || { echo "ABORT: Cycle 9 NNUE not found (0035)"; exit 3; }
[ -n "$V5" ]     && [ -f "$V5" ]     || { echo "ABORT: v5 NNUE not found (0018)";     exit 3; }

echo "Cycle 9 (1M): $CYCLE9"
echo "v5:           $V5"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo "=== bench depth 6, 3 pairs ==="
START=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$CYCLE9" "$V5" 6 3 2>&1 | tee "$ART/bench-depth6.log"
WALL_D6=$(( $(date +%s) - START ))

echo "=== bench depth 10, 3 pairs ==="
START=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$CYCLE9" "$V5" 10 3 2>&1 | tee "$ART/bench-depth10.log"
WALL_D10=$(( $(date +%s) - START ))

RATE_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-depth6.log"  | head -1 | awk '{print $3}')
RATE_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-depth10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0036 CYCLE-9 1M vs V5 VERDICT"
echo "=========================================================="
echo "  depth 6:  rate=$RATE_D6   wall=${WALL_D6}s"
echo "  depth 10: rate=$RATE_D10  wall=${WALL_D10}s"
echo
if   awk -v r="$RATE_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "  SOLID GAIN — v5-labelling marche. Cycle 10 envisageable."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "  MARGINAL — pivoter vers archi/encoding (0037)."
else
    echo "  REGRESSION — debug pipeline."
fi
echo "=========================================================="
