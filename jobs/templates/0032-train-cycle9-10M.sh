#!/usr/bin/env bash
# id: 0032-train-cycle9-10M
# description: Train the Cycle 9 NNUE on the 10M self-play corpus produced
#              by 0030a-d + merged by 0031. Recipe IDENTICAL to 0018
#              (Cycle 8 v5 BCE hybrid loss) — the only variable is the
#              corpus (10× larger, labelled by v5 NNUE instead of the
#              pre-Cycle-8 Linear that labelled 0010's 1M).
#
#              Architectures swept: 64-32, 128-64, 256-128, 512-256,
#              1024-512. Best by validation MSE is quantised + benched.
#
#              Reads:
#                /root/jass/jobs/results/0031-merge-cycle9-10M/
#                  artefacts.src/cycle9-10M.bin
#                /root/jass/jobs/results/0014-fetch-master-games/
#                  artefacts.src/master-1600.jnnw
# expected_duration: ~3-6 hours on 4 vCPU CCX23 (10× larger dataset
#                    than 0018's 1M; training scales sublinearly thanks
#                    to PyTorch's batched ops but still ~6-10× longer
#                    than 0018's 30-60 min).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0032-train-cycle9-10M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0031-merge-cycle9-10M/artefacts.src/cycle9-10M.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

if [ ! -f "$DATASET" ]; then
    echo "ABORT: Cycle 9 10M dataset $DATASET not found — did 0031 finish?"
    exit 3
fi
if [ ! -f "$MASTER" ]; then
    echo "ABORT: master JNNW $MASTER not found — did 0014 finish?"
    exit 3
fi

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2 {print $4" free of "$2}')"
echo "self-play dataset: $(ls -lh "$DATASET" | awk '{print $5"  "$9}')"
echo "master dataset:    $(ls -lh "$MASTER"  | awk '{print $5"  "$9}')"

echo
echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass: $(./build/jass --version)"

if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 10 ]; then
    echo "ABORT: less than 10 GB free on /; 10M training intermediate"
    echo "       checkpoints want more headroom"
    exit 3
fi

echo
echo "=== verifying Python deps ==="
if ! python3 -c "import torch, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    pip_ok=0
    for attempt in 1 2 3; do
        echo "  pip attempt $attempt/3"
        if TMPDIR="$PIP_SCRATCH" pip3 install \
                --break-system-packages --no-cache-dir --quiet \
                numpy torch --index-url https://download.pytorch.org/whl/cpu; then
            pip_ok=1; break
        fi
        sleep 10
    done
    rm -rf "$PIP_SCRATCH"
    [ "$pip_ok" -eq 1 ] || { echo "ABORT: pip failed"; exit 3; }
fi
python3 -c "import torch, numpy; print(f'  torch {torch.__version__}'); print(f'  numpy {numpy.__version__}')"

# Same hyper-parameters as 0018/0027 — corpus is the only variable.
MASTER_WEIGHT=1.0
MASTER_LAM=0.0
MASTER_LOSS=bce
WDL_SCALE=400
BCE_SCALE=50000

echo
echo "=== step 1/4: training Cycle 9 candidate (5 archs, BCE hybrid) ==="
echo "  self-play: $DATASET (10M, v5-labelled)"
echo "  master:    $MASTER"
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$DATASET" \
    --master-data         "$MASTER" \
    --master-weight       "$MASTER_WEIGHT" \
    --master-lam          "$MASTER_LAM" \
    --master-loss         "$MASTER_LOSS" \
    --wdl-scale           "$WDL_SCALE" \
    --bce-scale           "$BCE_SCALE" \
    --max-master-records  2000000 \
    --archs               64-32 128-64 256-128 512-256 1024-512 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train_v3 failed"; exit 4; }

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
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: quantize failed"; exit 5; }
ls -lh "$QUANT_OUT"

echo
echo "=== step 4/4: smoke benchmark cycle9 vs handcrafted (depth 6) ==="
./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench.log"

echo
echo "=========================================================="
echo "             0032 TRAIN CYCLE-9 10M SUMMARY"
echo "=========================================================="
echo "  self-play corpus:   $(stat -c%s "$DATASET" | awk '{print int(($1-8)/38)}') records (v5-labelled, 0031)"
echo "  master corpus:      $(stat -c%s "$MASTER"  | awk '{print int(($1-8)/38)}') records (0014)"
echo "  recipe:             same as 0018 (Cycle 8 v5 BCE hybrid)"
echo "  best arch:          $BEST_ARCH"
echo "  train wall:         ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/3600,2))")h)"
echo "  vs handcrafted:     $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  v5 vs handcrafted:  0.852 / +304 ELO (reference, 0018)"
echo "=========================================================="
echo
echo "Next: 0033 — bench Cycle 9 vs v5 head-to-head for the final ELO verdict."
