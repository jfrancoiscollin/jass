#!/usr/bin/env bash
# id: 0076-scan-distill-256-128-pure
# description: Diagnostic capacity vs data. Pure distillation 100K Scan
#              d12 → train sur 256-128 archi (~150K params vs 362K du
#              512-256). Ratio data/params passe de 0.28 à 0.67.
#
# Hypothèse à tester : 100K records est-il trop petit pour 512-256
# (val RMSE 212 cp dans 0075 → sous-fit). Si 256-128 atteint val RMSE
# significativement plus bas, hypothèse confirmée et on scale-up.
# Si 256-128 fail aussi (no legal move, vs Scan = 0/54), bug ailleurs.
#
# Réutilise le dataset distillé de 0073-0075 (zéro re-relabel).
#
# expected_duration: ~10-15 min (train ~2 min, bench ~8-10 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0076-scan-distill-256-128-pure"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

for CANDIDATE in \
    /root/jass/jobs/results/0075-scan-distillation-pure-no-master/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0074-scan-distillation-pilot-master-bce-fix/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0073-scan-distillation-pilot/artefacts.src/v10-distilled-100K.bin
do
    if [ -f "$CANDIDATE" ]; then
        RELAB_SRC="$CANDIDATE"
        break
    fi
done
[ -n "${RELAB_SRC:-}" ] || { echo "ABORT: no distilled dataset found"; exit 3; }

RELAB="$ART/v10-distilled-100K.bin"
cp "$RELAB_SRC" "$RELAB"
echo "Using distilled dataset : $RELAB_SRC"

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

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

echo
echo "=========================================================="
echo "=== train v10 256-128 PURE distillation ==="
echo "=========================================================="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$RELAB" \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --archs               256-128 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

V10_BIN="$ART/nnue-256-128.bin"
V10_Q="$ART/nnue-256-128-q.bin"
python3 tools/quantize_mlp.py --in "$V10_BIN" --data "$RELAB" --out "$V10_Q" \
    2>&1 | tee "$ART/quantize.log"

echo
echo "=========================================================="
echo "=== bench v10-256-128 vs Scan / v6 / v7 / v8 d10 ==="
echo "=========================================================="

python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V10_Q" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
RATE_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
RATE_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
RATE_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

# Extract val MSE for direct comparison vs 0075.
VAL_MSE=$(grep -oE 'val MSE\s+val RMSE' -A1 "$ART/train.log" | tail -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0076 SCAN DISTILL 256-128 PURE VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s"
echo "  vs Scan d10 : $RATE_SCAN"
echo "  vs v6 d10   : $RATE_V6"
echo "  vs v7 d10   : $RATE_V7"
echo "  vs v8 d10   : $RATE_V8"
echo
echo "  Comparaison capacité :"
echo "    0075 (512-256, 362K params) : val RMSE 212, vs Scan 0.000, vs v8 0.111"
echo "    0076 (256-128, 150K params) : val RMSE $VAL_MSE, vs Scan $RATE_SCAN, vs v8 $RATE_V8"
echo
echo "  Decision :"
echo "    * 256-128 vs v8 > 0.40 → capacity était le bug, scale up data ou archi"
echo "    * 256-128 ≈ 0075 (~0.10) → bug ailleurs (data, pipeline, search)"
echo "                                → debug profond ou drop distillation"
echo "=========================================================="
