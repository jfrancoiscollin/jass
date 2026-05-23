#!/usr/bin/env bash
# id: 0025a-4-train-bigger-arch
# description: Tente une archi plus grosse (1024-512 ou 2048-1024) sur
#              le 0010 1M EXISTANT + master blend. Pas de nouveau
#              gen-data — donc compute trivial (~30-90 min de training
#              sur 4 vCPU, ~€0.10).
#
#              Hypothèse: notre 256-128 MLP sature; un réseau 2-4× plus
#              gros gagnera +30-80 ELO même sans corpus plus gros.
#              Stockfish a fait exactement ce saut entre NNUE 256x2
#              et 1024x2 → +100 ELO sans changer le corpus.
#
#              Cost contrôlé pour comparer head-to-head vs v5:
#                * MÊME corpus (0010 1M + master-1600)
#                * MÊME loss (BCE hybride)
#                * Variable unique: l'archi.
#
#              Seules les archs PLUS GROSSES que 256-128 sont
#              entraînées ici: 512-256, 1024-512, 2048-1024 (les
#              petites sont déjà dans 0018).
# expected_duration: ~1-3 h sur 4 vCPU CCX23 (3 archs × ~30 min chacune
#                    en moyenne; 2048-1024 est le plus lent ~1.5 h).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-4-train-bigger-arch"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"

[ -f "$DATASET" ] || { echo "ABORT: 0010 dataset not found: $DATASET"; exit 3; }
[ -f "$MASTER" ]  || { echo "ABORT: master not found: $MASTER"; exit 3; }

echo "=== host facts ==="
echo "host:    $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

echo "=== rebuilding jass ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -3

if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 5 ]; then
    echo "ABORT: less than 5 GB free on /"
    exit 3
fi

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

# Same hyperparameters as 0018 — only the archs change.
MASTER_WEIGHT=1.0
MASTER_LAM=0.0
MASTER_LOSS=bce
WDL_SCALE=400
BCE_SCALE=50000

echo "=== training bigger archs (512-256, 1024-512, 2048-1024) ==="
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
    --archs               512-256 1024-512 2048-1024 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

# Quantise each bigger arch — best by val MSE is the candidate to bench.
echo "=== quantising all bigger archs ==="
for arch in 512-256 1024-512 2048-1024; do
    BIN="$ART/nnue-${arch}.bin"
    [ -f "$BIN" ] || { echo "  warn: $BIN missing, skipping"; continue; }
    python3 tools/quantize_mlp.py --in "$BIN" --data "$DATASET" \
        --out "$ART/nnue-${arch}-q.bin" \
        2>&1 | tail -3
done

BEST_ARCH=$(python3 -c "
import json
with open('$ART/summary.json') as f: s = json.load(f)
print(sorted(s.items(), key=lambda kv: kv[1]['val_mse'])[0][0])
")
QUANT_BEST="$ART/nnue-${BEST_ARCH}-q.bin"

echo "=== smoke bench (best arch only) vs handcrafted ==="
./build/jass --benchmark-nnue "$QUANT_BEST" 2>&1 | tee "$ART/bench.log"

echo
echo "=========================================================="
echo "       0037 BIGGER ARCH (0010 1M) SUMMARY"
echo "=========================================================="
echo "  corpus:           0010 1M (depth-20 Linear-labelled) + master"
echo "  archs trained:    512-256, 1024-512, 2048-1024"
echo "  best arch (val MSE): $BEST_ARCH"
echo "  train wall:       ${TRAIN_SEC}s"
echo "  vs handcrafted:   $(grep 'NNUE score rate' "$ART/bench.log" | tail -1)"
echo "  v5 (256-128):     0.852 / +304 ELO vs handcrafted (reference)"
echo "=========================================================="
echo
echo "Next: 0038-bench-bigger-arch-vs-v5 — head-to-head, decision."
