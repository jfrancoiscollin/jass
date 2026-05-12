#!/usr/bin/env bash
# id: 0011-train-and-bench
# description: NNUE training pipeline on the 1M depth-20 dataset
#              produced by 0010. Trains 5 MLP archs (64-32, 128-64,
#              256-128, 512-256, 1024-512) under the HalfMen-lite
#              encoding (input_dim=450, Cycle-6c, the target arch)
#              via train_v3.py, picks the best by val MSE, quantises
#              it to int8, then runs the built-in NNUE-vs-handcrafted
#              benchmark to estimate strength.
#
#              1024-512 (~720K params, ratio 1.4 records/param at 1M)
#              is included as an overfit canary: its val_mse vs
#              512-256 is the gate for the 10M decision — if it
#              regresses, 10M is justified; if it wins, 1M is already
#              under-parameterised.
#
#              Self-installs torch+numpy if the CCX23 didn't get them
#              from bootstrap (INSTALL_TORCH is opt-in there).
# expected_duration: ~5-14 h on 4 vCPU CCX23 (1024-512 dominates;
#                    other archs finish in minutes to ~2 h each)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0011-train-and-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
if [ ! -f "$DATASET" ]; then
    echo "ABORT: $DATASET not found — 0010 didn't finish, or its merge step failed."
    echo "Available files under 0010 artefacts.src:"
    ls -la "$(dirname "$DATASET")" 2>/dev/null || echo "  (directory missing)"
    exit 3
fi

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2{print $4 \" free of \" $2}')"
echo "load:    $(cut -d' ' -f1-3 /proc/loadavg)"
echo "jass:    $(./build/jass --version 2>/dev/null || echo '(no --version)')"
echo "dataset: $(ls -lh \"$DATASET\" | awk '{print $5\"  \"$9}')"

if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 5 ]; then
    echo "ABORT: less than 5 GB free on /, refusing to start (torch wheel ~700 MB + scratch)"
    exit 3
fi

echo
echo "=== verifying Python deps ==="
if ! python3 -c "import torch, numpy" 2>/dev/null; then
    echo "torch/numpy missing — installing CPU wheels (~700 MB, one-shot)"
    pip3 install --break-system-packages --quiet \
        numpy torch --index-url https://download.pytorch.org/whl/cpu \
        || { echo "ABORT: pip install failed"; exit 3; }
fi
python3 -c "import torch, numpy; print(f'  torch {torch.__version__}'); print(f'  numpy {numpy.__version__}')"

echo
echo "=== step 1/4: training 5 archs on 1M records (HalfMen encoding) ==="
echo "  archs:    64-32, 128-64, 256-128, 512-256, 1024-512"
echo "            (1024-512 is a deliberate overfit canary for the"
echo "             10M decision: its val_mse vs 512-256 tells us"
echo "             whether more data would help or hurt)"
echo "  encoding: halfmen (input_dim=450)"
echo "  epochs:   30, batch: 512, lambda: 0.7 (default)"
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data     "$DATASET" \
    --archs    64-32 128-64 256-128 512-256 1024-512 \
    --encoding halfmen \
    --epochs   30 \
    --batch    512 \
    --out-dir  "$ART" \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
echo "train rc=$TRAIN_RC wall=${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/3600,2))")h)"
if [ "$TRAIN_RC" -ne 0 ]; then
    echo "ABORT: train_v3 failed"
    exit 4
fi

BEST_ARCH=$(python3 -c "
import json
with open('$ART/summary.json') as f: s = json.load(f)
print(sorted(s.items(), key=lambda kv: kv[1]['val_mse'])[0][0])
")
echo
echo "=== step 2/4: best arch by val MSE = $BEST_ARCH ==="
BEST_BIN="$ART/nnue-${BEST_ARCH}.bin"
ls -lh "$BEST_BIN"

echo
echo "=== step 3/4: quantising $BEST_ARCH to int8 ==="
QUANT_OUT="$ART/nnue-${BEST_ARCH}-q.bin"
python3 tools/quantize_mlp.py \
    --in   "$BEST_BIN" \
    --data "$DATASET" \
    --out  "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"
QUANT_RC=${PIPESTATUS[0]}
if [ "$QUANT_RC" -ne 0 ]; then
    echo "ABORT: quantize_mlp failed"
    exit 5
fi
ls -lh "$QUANT_OUT"

echo
echo "=== step 4/4: benchmark NNUE($BEST_ARCH int8) vs handcrafted ==="
./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench.log"

echo
echo "=========================================================="
echo "                0011 TRAIN+BENCH SUMMARY"
echo "=========================================================="
echo "  dataset records:  1 000 000 @ depth 20 (from 0010)"
echo "  encoding:         halfmen (input_dim=450, Cycle-6c)"
echo "  best arch:        $BEST_ARCH"
echo "  train wall:       ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/3600,2))")h)"
echo "  bench result:     $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  artefacts:        $(ls "$ART" | wc -l) files, $(du -sh "$ART" | awk '{print $1}') total"
echo "=========================================================="
