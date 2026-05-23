#!/usr/bin/env bash
# id: 0042-train-pattern-v1
# description: First-principles pattern-based eval prototype (Scan/
#              Kingsrow-inspired). Trains the v1 PatternNetwork (8
#              patterns × 4 squares = 5000 weights) on the 0010 1M
#              depth-20 dataset. Benches vs handcrafted and vs v5
#              to test whether the architectural shift breaks the
#              -812 ELO plateau or just re-validates the dense MLP
#              direction.
#
#              v1 pattern set is intentionally minimal (~5% the
#              weights of the current MLPNetworkQ at 150K) — proves
#              the pipeline. If the bench shows ANY upside vs
#              handcrafted, the architecture is on the right track
#              and v2 (16 patterns × 8 squares = 6.25M weights, full
#              Scan-class) becomes the priority.
#
#              Reads:
#                /root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/
#                  artefacts.src/depth20-1M.bin
#
# expected_duration: ~20-40 min on 4 vCPU CCX23. Pattern training is
#                    cheap (5000 fp32 weights vs ~150K for MLP).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0042-train-pattern-v1"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo "=== pip ==="
if ! python3 -c "import torch, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages --no-cache-dir --quiet \
            numpy torch --index-url https://download.pytorch.org/whl/cpu && break
        sleep 10
    done
    rm -rf "$PIP_SCRATCH"
fi

echo "=== train v1 pattern net ==="
OUT_JPAT="$ART/pattern-v1.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data    "$DATASET" \
    --out     "$OUT_JPAT" \
    --epochs  30 \
    --batch   4096 \
    --lr      1e-2 \
    --lambda  0.7 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

echo "=== bench v1 pattern vs handcrafted (depth 6) ==="
./build/jass --benchmark-nnue "$OUT_JPAT" 2>&1 | tee "$ART/bench-vs-hc.log"

echo "=== bench v1 pattern vs v5 NNUE (depth 6, 3 pairs) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 6 3 \
    2>&1 | tee "$ART/bench-vs-v5-d6.log"

echo "=== bench v1 pattern vs v5 NNUE (depth 10, 3 pairs) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 10 3 \
    2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0042 PATTERN v1 (8×4) VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s"
echo "  weights:              5000 (vs ~150K for MLPNetworkQ 256-128)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  Reference v5 (256-128 MLP) vs handcrafted: 0.852 / +304 ELO"
echo
echo "  Reading:"
echo "    rate_v5_d10 > 0.40  → pattern archi prometteur malgré 5×"
echo "                         moins de params; scale-up v2 (16×8)"
echo "                         devient prioritaire."
echo "    rate_v5_d10 ∈ [0.20, 0.40] → match attendu pour v1 minimal."
echo "                         v2 vaut le coup d'essayer."
echo "    rate_v5_d10 < 0.20  → patterns 4-square ne capturent rien."
echo "                         Soit le pattern set est trop petit, soit"
echo "                         le training est cassé. Debug avant v2."
echo "=========================================================="
