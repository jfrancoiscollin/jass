#!/usr/bin/env bash
# id: 0027-train-cycle9-pilot
# description: Train a Cycle 9 candidate NNUE on the 100K single-host
#              pilot dataset produced by 0025a (down from 500K after we
#              discovered the v5 MLP labeller is ~13× slower than the
#              embedded Linear used in 0010 — 500K @ depth 20 would have
#              taken 36 days). The whole purpose of Cycle 9 is to test
#              whether relabelling self-play data with v5 yields a
#              strictly better corpus and therefore a better "v6" NNUE.
#
#              Recipe is EXACTLY the same as 0018 (Cycle 8 BCE hybrid
#              loss) except the self-play dataset is swapped — that
#              keeps the loss-form variable fixed so any ELO delta
#              measured by 0028 is attributable to the corpus, not
#              the training recipe.
#
#              100K + depth 16 will give a noisy signal: Cycle 8 v5 trained
#              on 1M @ depth 20 for +249 ELO; the pilot here at 10× less
#              data + lower depth labels should show at least a +30-50 ELO
#              shift if the v5-labelling premise holds. A clearly positive
#              signal here is the go/no-go for the full 10M run.
#
#              Reads:
#                /root/jass/jobs/results/0025a-cycle9-pilot-host-a/
#                  artefacts.src/host-a.bin            (100K, v5-labelled, depth 16)
#                /root/jass/jobs/results/0014-fetch-master-games/
#                  artefacts.src/master-1600.jnnw     (master blend)
# expected_duration: ~15-30 min on 4 vCPU CCX23 (small dataset, fast train).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0027-train-cycle9-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0025a-cycle9-pilot-host-a/artefacts.src/host-a.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

if [ ! -f "$DATASET" ]; then
    echo "ABORT: Cycle 9 pilot dataset $DATASET not found — did 0025a finish?"
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
echo "jass: $(./build/jass --version 2>/dev/null)"

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

# Same hyperparameters as 0018 (v5). Keeping these fixed isolates the
# corpus as the only variable, so 0028's NNUE-vs-NNUE benchmark cleanly
# answers "does relabelling self-play with v5 improve training?".
MASTER_WEIGHT=1.0
MASTER_LAM=0.0
MASTER_LOSS=bce
WDL_SCALE=400
BCE_SCALE=50000

echo
echo "=== step 1/4: training Cycle 9 candidate (5 archs, hybrid loss) ==="
echo "  self-play: $DATASET (1M, v5-labelled — Cycle 9 corpus)"
echo "  master:    $MASTER"
echo "  loss form: self-play MSE + master BCE"
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
echo "             0027 TRAIN CYCLE-9 PILOT SUMMARY"
echo "=========================================================="
echo "  self-play corpus:   $(stat -c%s "$DATASET" | awk '{print int(($1-8)/38)}') records (v5-labelled, 0025a single-host pilot)"
echo "  master corpus:      $(stat -c%s "$MASTER"  | awk '{print int(($1-8)/38)}') records (0014, blended)"
echo "  recipe:             same as 0018 (Cycle 8 v5 BCE hybrid)"
echo "  best arch:          $BEST_ARCH"
echo "  train wall:         ${TRAIN_SEC}s"
echo "  vs handcrafted:     $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  v5 vs handcrafted:  0.852 / +304 ELO (reference, 0018)"
echo "=========================================================="
echo
echo "Next: 0028 — direct nnue-vs-nnue match (Cycle 9 vs v5) to compute"
echo "the corpus-relabelling delta. >0.52 score rate ⇒ Cycle 9 corpus"
echo "strictly improves over the pre-v5-labelled 0010 corpus."
