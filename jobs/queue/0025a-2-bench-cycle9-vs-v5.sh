#!/usr/bin/env bash
# id: 0025a-2-bench-cycle9-vs-v5
# description: Cycle 9 pilot verdict — direct head-to-head between the
#              Cycle 9 candidate NNUE (trained on the v5-labelled 1M
#              corpus produced by 0025a+0027 single-host pilot) and v5 (0018).
#              Same recipe, same hyper-params, same handcrafted opening
#              pool — the only variable is the self-play dataset, so
#              the score rate measures the corpus quality directly.
#
#              Reads:
#                /root/jass/jobs/results/0025a-1-train-cycle9-pilot/
#                  artefacts.src/nnue-*-q.bin           (Cycle 9 quantised)
#                /root/jass/jobs/results/0018-train-with-master-bce/
#                  artefacts.src/nnue-*-q.bin           (v5 quantised)
#
#              Decision table:
#                rate > 0.55 (≈ +35 ELO)  → strong corpus gain, GO 10M.
#                rate ∈ [0.52, 0.55]       → marginal gain, GO 10M anyway
#                                            (the pilot under-represents
#                                            the gain we'd see at 10× the
#                                            volume — more data helps more).
#                rate ∈ [0.48, 0.52]       → no gain. Don't pay for 10M.
#                                            Investigate (was v5 already at
#                                            the labeller-quality ceiling?
#                                            different bottleneck?).
#                rate < 0.48               → REGRESSION. Hard stop, debug.
# expected_duration: ~30-60 min on 4 vCPU CCX23 (depth 6, ~18-54 games).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-2-bench-cycle9-vs-v5"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

CYCLE9=$(ls -t /root/jass/jobs/results/0025a-1-train-cycle9-pilot/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(    ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

if [ -z "$CYCLE9" ] || [ ! -f "$CYCLE9" ]; then
    echo "ABORT: Cycle 9 NNUE not found — did 0027 finish?"
    exit 3
fi
if [ -z "$V5" ] || [ ! -f "$V5" ]; then
    echo "ABORT: v5 NNUE not found (0018)"
    exit 3
fi

echo "=== host facts ==="
echo "host:  $(hostname)"
echo "nproc: $(nproc)"
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
echo "=== NNUE-vs-NNUE: Cycle 9 (A) vs v5 (B), depth 10, 3 pairs (slower, more accurate) ==="
START=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$CYCLE9" "$V5" 10 3 \
    2>&1 | tee "$ART/bench-depth10.log"
WALL_D10=$(( $(date +%s) - START ))

# Extract score rates with light grep parsing.
RATE_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-depth6.log"  | head -1 | awk '{print $3}')
RATE_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-depth10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0028 CYCLE-9 vs V5 PILOT VERDICT"
echo "=========================================================="
echo "  Cycle 9:           $(basename "$CYCLE9")"
echo "  v5:                $(basename "$V5")"
echo "  depth 6:           rate=$RATE_D6  wall=${WALL_D6}s"
echo "  depth 10:          rate=$RATE_D10 wall=${WALL_D10}s"
echo
echo "  Decision:"
if   awk -v r="$RATE_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    STRONG GAIN — Cycle 9 corpus strictly better than 0010."
    echo "    RECOMMENDATION: scale up to the full 10M run on 4-8× CPX62."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r > 0.52) }'; then
    echo "    MARGINAL GAIN — corpus better, but the pilot under-represents"
    echo "    the asymptote. At 10× the volume the delta should grow."
    echo "    RECOMMENDATION: still GO 10M (cheap relative to upside)."
elif awk -v r="$RATE_D10" 'BEGIN { exit !(r >= 0.48) }'; then
    echo "    NO GAIN — v5 may already be at the labeller-quality ceiling."
    echo "    RECOMMENDATION: don't pay €188+ for the 10M. Investigate"
    echo "    other bottlenecks (architecture, training recipe, book)."
else
    echo "    REGRESSION — Cycle 9 corpus is worse than 0010 at 1M."
    echo "    RECOMMENDATION: hard stop. Debug pipeline (was v5 really"
    echo "    used as labeller? sanity-check shard logs)."
fi
echo "=========================================================="
