#!/usr/bin/env bash
# id: 0040-train-cycle9-1M-depth10
# description: Train NNUE sur le 1M v5-labelled @ depth 10 produit par
#              0039. Recipe identique à 0018/0035 — seule variable :
#              EVAL_DEPTH du dataset source (10 vs 16 vs 20).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0040-train-cycle9-1M-depth10"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0039-cycle9-1M-depth10-singlehost/artefacts.src/cycle9-1M-depth10.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found (0039 missing)"; exit 3; }
[ -f "$MASTER" ]  || { echo "ABORT: $MASTER not found"; exit 3; }

echo "host: $(hostname)  nproc: $(nproc)"

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

# Same hyperparameters as 0018/0035 — only the corpus changes.
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$DATASET" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  2000000 \
    --archs               64-32 128-64 256-128 512-256 1024-512 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

BEST_ARCH=$(python3 -c "
import json
with open('$ART/summary.json') as f: s = json.load(f)
print(sorted(s.items(), key=lambda kv: kv[1]['val_mse'])[0][0])
")
BEST_BIN="$ART/nnue-${BEST_ARCH}.bin"
QUANT_OUT="$ART/nnue-${BEST_ARCH}-q.bin"

python3 tools/quantize_mlp.py --in "$BEST_BIN" --data "$DATASET" --out "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"

./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench.log"

echo
echo "=========================================================="
echo "       0040 TRAIN CYCLE-9 1M @ DEPTH 10 SUMMARY"
echo "=========================================================="
echo "  corpus depth:     10 (vs 16 dans 0035, 20 dans 0018 référence)"
echo "  best arch:        $BEST_ARCH"
echo "  train wall:       ${TRAIN_SEC}s"
echo "  vs handcrafted:   $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  v5 reference:     0.852 / +304 ELO"
echo "=========================================================="
