#!/usr/bin/env bash
# id: 0035-train-cycle9-1M
# description: Train Cycle 9 NNUE sur le 1M v5-labelled produit par
#              0034. Recipe identique à 0018 (BCE hybride + master
#              blend) — seule variable: le corpus self-play (1M
#              v5-labelled vs 1M Linear-labelled de 0010).
#
#              Si 0036 montre Cycle 9 > v5 d'au moins +20-30 ELO, on a
#              validé le v5-labelling.
# expected_duration: ~30-60 min sur 4 vCPU CCX23.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0035-train-cycle9-1M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0034-cycle9-1M-singlehost/artefacts.src/cycle9-1M.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -f "$MASTER" ]  || { echo "ABORT: $MASTER not found"; exit 3; }

echo "=== host facts ==="
echo "host:    $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

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
python3 -c "import torch, numpy; print(f'  torch {torch.__version__}, numpy {numpy.__version__}')"

# Same hyperparameters as 0018 (Cycle 8 v5 BCE).
MASTER_WEIGHT=1.0
MASTER_LAM=0.0
MASTER_LOSS=bce
WDL_SCALE=400
BCE_SCALE=50000

echo "=== training Cycle 9 (5 archs, BCE hybride) ==="
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
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

BEST_ARCH=$(python3 -c "
import json
with open('$ART/summary.json') as f: s = json.load(f)
print(sorted(s.items(), key=lambda kv: kv[1]['val_mse'])[0][0])
")
BEST_BIN="$ART/nnue-${BEST_ARCH}.bin"
QUANT_OUT="$ART/nnue-${BEST_ARCH}-q.bin"

echo "=== quantising $BEST_ARCH ==="
python3 tools/quantize_mlp.py --in "$BEST_BIN" --data "$DATASET" --out "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"

echo "=== smoke bench vs handcrafted ==="
./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench.log"

echo
echo "=========================================================="
echo "             0035 TRAIN CYCLE-9 1M SUMMARY"
echo "=========================================================="
echo "  corpus:           1M v5-labelled (from 0034)"
echo "  recipe:           same as 0018 (BCE hybride)"
echo "  best arch:        $BEST_ARCH"
echo "  train wall:       ${TRAIN_SEC}s"
echo "  vs handcrafted:   $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  v5 reference:     0.852 / +304 ELO vs handcrafted"
echo "=========================================================="
