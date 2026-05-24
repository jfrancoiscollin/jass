#!/usr/bin/env bash
# id: 0033-bench-cycle9-10M-vs-v5
# description: Final ELO verdict for the Cycle 9 10M run. Head-to-head
#              between the Cycle 9 candidate NNUE (trained on the
#              v5-labelled 10M from 0032) and v5 itself (0018). Same
#              recipe, same hyper-params, same handcrafted opening
#              pool — the only variable is the self-play corpus.
#
#              Reads:
#                /root/jass/jobs/results/0032-train-cycle9-10M/
#                  artefacts.src/nnue-*-q.bin            (Cycle 9, 10M)
#                /root/jass/jobs/results/0018-train-with-master-bce/
#                  artefacts.src/nnue-*-q.bin            (v5)
#
#              Decision table (depth 10 score rate, 18 games):
#                > 0.60 (≈ +70 ELO)  → BIG WIN. Promote Cycle 9 NNUE
#                                       to default. Plan Cycle 10.
#                [0.55, 0.60]         → SOLID GAIN. Ship Cycle 9.
#                [0.50, 0.55]         → MARGINAL. Cycle 9 is the new
#                                       default but the 10M wasn't
#                                       the unlock — bottleneck is
#                                       elsewhere (architecture, book,
#                                       master-blend ratio…).
#                [0.45, 0.50]         → FLAT. The 10M v5-labelling
#                                       didn't add anything detectable.
#                                       Stop scaling self-play; pivot.
#                < 0.45               → REGRESSION. Debug — likely a
#                                       training-pipeline bug (param
#                                       drift, dataset corruption).
# expected_duration: ~45-90 min on 4 vCPU CCX23.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0033-bench-cycle9-10M-vs-v5"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

CYCLE9=$(ls -t /root/jass/jobs/results/0032-train-cycle9-10M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(    ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

if [ -z "$CYCLE9" ] || [ ! -f "$CYCLE9" ]; then
    echo "ABORT: Cycle 9 NNUE not found — did 0032 finish?"
    exit 3
fi
if [ -z "$V5" ] || [ ! -f "$V5" ]; then
    echo "ABORT: v5 NNUE not found (0018)"
    exit 3
fi

echo "=== host facts ==="
echo "host:         $(hostname)"
echo "nproc:        $(nproc)"
echo "Cycle 9 NNUE: $CYCLE9 ($(stat -c%s "$CYCLE9") B)"
echo "v5 NNUE:      $V5 ($(stat -c%s "$V5") B)"

echo
echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5

echo
echo "=== NNUE-vs-NNUE: Cycle 9 (A) vs v5 (B), depth 6, 3 pairs ==="
START=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$CYCLE9" "$V5" 6 3 \
    2>&1 | tee "$ART/bench-depth6.log"
WALL_D6=$(( $(date +%s) - START ))

echo
echo "=== NNUE-vs-NNUE: Cycle 9 (A) vs v5 (B), depth 10, 3 pairs ==="
START=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$CYCLE9" "$V5" 10 3 \
    2>&1 | tee "$ART/bench-depth10.log"
WALL_D10=$(( $(date +%s) - START ))

RATE_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-depth6.log"  | head -1 | awk '{print $3}')
RATE_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-depth10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0033 CYCLE-9 10M vs V5 FINAL VERDICT"
echo "=========================================================="
echo "  Cycle 9 (10M): $(basename "$CYCLE9")"
echo "  v5:            $(basename "$V5")"
echo "  depth 6:       rate=$RATE_D6   wall=${WALL_D6}s"
echo "  depth 10:      rate=$RATE_D10  wall=${WALL_D10}s"
echo
echo "  Decision:"
if   awk -v r="$RATE_D10" 'BEGIN { exit !(r > 0.60) }'; then
    echo "    BIG WIN — Cycle 9 corpus strictly better than v5."
    echo "    Promote to default NNUE. Plan Cycle 10."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    SOLID GAIN — ship Cycle 9."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    MARGINAL — Cycle 9 is the new default but the 10M wasn't"
    echo "    the bottleneck. Reassess architecture / blend / book."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r >= 0.45) }'; then
    echo "    FLAT — 10M v5-labelling didn't detectably help."
    echo "    Stop scaling self-play; pivot strategy."
else
    echo "    REGRESSION — debug pipeline (param drift, corruption)."
fi
echo "=========================================================="
