#!/usr/bin/env bash
# id: 0018-train-with-master-bce
# description: Cycle 8 v5 — train NNUE with the HYBRID loss form
#              (self-play MSE + master BCE). The prior v1-v4 runs all
#              used pure MSE on master records with target = wdl × 800,
#              which dragged the network's cp distribution into a
#              bimodal regime and regressed the 1.0 s/move bench from
#              0.58 (baseline) → 0.472 (master-blend v4).
#
#              v5 splits the loss by record source:
#                self-play → blended score+WDL MSE (unchanged)
#                master    → binary cross-entropy on
#                            sigmoid(pred/wdl_scale) vs (wdl+1)/2
#              The BCE arm only cares about the SIGN/probability of
#              the prediction, not its cp magnitude, so master records
#              polarise the eval without dictating its scale.
#
#              Prerequisite chain: 0010 → 0014 (fetch master) → 0018
#              (this job). 0014's master-1600.jnnw on the server is
#              re-used as-is — no re-fetch needed.
#
# expected_duration: ~30-60 min on 4 vCPU CCX23 (same shape as 0016).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0018-train-with-master-bce"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
# Cycle 8 v3 (2026-05-19): switched from master-2000.jnnw (~3.4K games,
# 371K positions) to master-1600.jnnw (43K games, 4.74M positions). The
# v2 run with master-2000 + master_weight=3.0 regressed the depth-6
# bench from 0.917 → 0.389 because the small master corpus, amplified
# 3×, dominated the loss with a bimodal ±800 WDL target that pulled
# the network away from the continuous score targets self-play provides.
# master-1600 is 12× larger by volume, so we can drop master_weight to
# 1.0 and let the natural ratio do the work.
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

if [ ! -f "$DATASET" ]; then
    echo "ABORT: self-play dataset $DATASET not found — did 0010 finish?"
    ls -la "$(dirname "$DATASET")" 2>/dev/null || echo "  (0010 dir missing)"
    exit 3
fi
if [ ! -f "$MASTER" ]; then
    echo "ABORT: master JNNW $MASTER not found — did 0014 finish?"
    ls -la "$(dirname "$MASTER")" 2>/dev/null || echo "  (0014 dir missing)"
    echo "Re-queue this job (delete jobs/results/0016-…/) once 0014 completes."
    exit 3
fi

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2 {print $4" free of "$2}')"
echo "load:    $(cut -d' ' -f1-3 /proc/loadavg)"
echo "jass:    $(./build/jass --version 2>/dev/null || echo '(no --version)')"
echo "self-play dataset: $(ls -lh "$DATASET" | awk '{print $5"  "$9}')"
echo "master dataset:    $(ls -lh "$MASTER"  | awk '{print $5"  "$9}')"

echo
echo "=== rebuilding jass (no-op if src/ unchanged since last build) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass after rebuild: $(./build/jass --version 2>/dev/null || echo '(no --version)')"

if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 5 ]; then
    echo "ABORT: less than 5 GB free on /, refusing to start"
    exit 3
fi

echo
echo "=== verifying Python deps ==="
if ! python3 -c "import torch, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    pip_ok=0
    for attempt in 1 2 3; do
        echo "  pip attempt $attempt/3 (TMPDIR=$PIP_SCRATCH, --no-cache-dir)"
        if TMPDIR="$PIP_SCRATCH" pip3 install \
                --break-system-packages --no-cache-dir --quiet \
                numpy torch --index-url https://download.pytorch.org/whl/cpu; then
            pip_ok=1
            break
        fi
        echo "  attempt $attempt failed, retrying after 10s"
        sleep 10
    done
    rm -rf "$PIP_SCRATCH"
    if [ "$pip_ok" -ne 1 ]; then
        echo "ABORT: pip install failed after 3 attempts"
        exit 3
    fi
fi
python3 -c "import torch, numpy; print(f'  torch {torch.__version__}'); print(f'  numpy {numpy.__version__}')"

# Cycle 8 v5 hyper-parameters (hybrid loss).
#   --master-loss bce    → master records use binary cross-entropy on
#                          sigmoid(pred/wdl_scale) vs (wdl+1)/2 instead
#                          of MSE on wdl×800. Decouples the master
#                          signal from the cp scale.
#   --wdl-scale 400      → standard chess/draughts WDL conversion
#                          (a 400 cp advantage ≈ 73% win probability).
#   --bce-scale 50000    → BCE→MSE-equivalent magnitude bridge so the
#                          optimiser sees comparable gradients from
#                          both arms.
#   --master-weight 1.0  → no artificial amplification; natural volume
#                          ratio (4.74M master vs 1M self-play, capped
#                          at 2M after subsample = ~67% master share).
#   --master-lam 0.0     → ignored when --master-loss=bce, but kept
#                          for consistency in the CLI.
MASTER_WEIGHT=1.0
MASTER_LAM=0.0
MASTER_LOSS=bce
WDL_SCALE=400
BCE_SCALE=50000

echo
echo "=== step 1/4: training 5 archs on hybrid-loss blended dataset ==="
echo "  self-play: $DATASET"
echo "  master:    $MASTER"
echo "  loss form: self-play MSE + master BCE (--master-loss=$MASTER_LOSS,"
echo "             --wdl-scale=$WDL_SCALE, --bce-scale=$BCE_SCALE)"
echo "  weight:    master_weight=$MASTER_WEIGHT  master_lam=$MASTER_LAM (ignored by BCE)"
echo "  archs:    64-32, 128-64, 256-128, 512-256, 1024-512"
echo "  encoding: halfmen (input_dim=450)"
echo "  epochs:   30, batch: 512, lambda: 0.7 (self-play)"
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
echo "             0018 TRAIN-WITH-MASTER-BCE SUMMARY"
echo "=========================================================="
echo "  self-play records:  $(stat -c%s "$DATASET" | awk '{print int(($1-8)/38)}' 2>/dev/null) (depth 20, from 0010)"
echo "  master records:     $(stat -c%s "$MASTER"  | awk '{print int(($1-8)/38)}' 2>/dev/null) (master games, from 0014)"
echo "  master loss form:   $MASTER_LOSS (wdl_scale=$WDL_SCALE, bce_scale=$BCE_SCALE)"
echo "  master weight:      $MASTER_WEIGHT"
echo "  master lam:         $MASTER_LAM (ignored when --master-loss=bce)"
echo "  encoding:           halfmen (input_dim=450)"
echo "  best arch:          $BEST_ARCH"
echo "  train wall:         ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/3600,2))")h)"
echo "  bench result:       $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  artefacts:          $(ls "$ART" | wc -l) files, $(du -sh "$ART" | awk '{print $1}') total"
echo "=========================================================="
echo
echo "Next step: re-queue 0012 (calibrate vs Scan) with the new NNUE"
echo "  to measure the cycle-8 ELO delta vs the 0011 baseline."
