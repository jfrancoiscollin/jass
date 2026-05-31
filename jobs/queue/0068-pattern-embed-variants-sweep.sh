#!/usr/bin/env bash
# id: 0068-pattern-embed-variants-sweep
# description: Paradigm shift (A) suite — sweep variants embed_dim × hidden
#              × pattern set pour identifier la meilleure config avant
#              port C++ JPAT v8.
#
# Baseline 0067 : v2 × d=4 × h=64 → pearson master +0.6109 (vs 0065 linear
# 0.28, 0066 MLP-head 0.12). Premier signal positif après 13 hypothèses
# flat. Avant d'engager 4-6h de port C++ on vérifie qu'on a la meilleure
# config Python.
#
# Sweep (5 configs, ~5 min/each train + pearson) :
#   v2 × d=4  × h=64   (baseline 0067, re-run pour sanity)
#   v2 × d=8  × h=64
#   v2 × d=8  × h=128
#   v3 × d=4  × h=64   (longer patterns, +29× params)
#   v3 × d=4  × h=128
#
# v3 × d=8/16 omis : 34-68M params sur 1M records = surfit assuré.
#
# Decision gate :
#   * meilleur pearson master > 0.65 → port C++ avec cette config
#   * meilleur pearson master ≈ 0.61 (plateau) → port C++ baseline 0067
#   * dégradation systématique avec capacité accrue → signe d'overfit,
#     baseline 0067 reste optimal pour port C++
#
# expected_duration: ~30-45 min sur 8 vCPU CCX33 :
#                    * 5 configs × ~3-5 min train + ~30s pearson
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0068-pattern-embed-variants-sweep"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V7" ] && [ -f "$V7" ] || { echo "ABORT: v7 NNUE not found"; exit 3; }

MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset    : $V8_DATA"
echo "v7 reference  : $V7"
echo "master sample : $MASTER_SAMPLE"

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

CONFIGS=(
    "v2 4  64"
    "v2 8  64"
    "v2 8  128"
    "v3 4  64"
    "v3 4  128"
)

RESULTS=""
for cfg in "${CONFIGS[@]}"; do
    set -- $cfg
    P="$1"; D="$2"; H="$3"
    TAG="$P-d$D-h$H"
    OUT_PT="$ART/embed-$TAG.pt"

    echo
    echo "=========================================================="
    echo "=== train $TAG ($P × embed_dim=$D × hidden=$H) ==="
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern_embed.py \
        --data "$V8_DATA" --out "$OUT_PT" \
        --patterns "$P" --embed-dim "$D" --mlp-hidden "$H" \
        --epochs 30 --batch 4096 --lr 1e-3 --lambda 0.7 \
        --score-scale 0.01 --weight-decay 1e-5 --val-frac 0.05 --seed 42 \
        2>&1 | tee "$ART/train-$TAG.log"
    TRAIN_SEC=$(( $(date +%s) - START ))

    PEARSON_M="-"
    PEARSON_S="-"
    if [ -f "$OUT_PT" ]; then
        python3 tools/pattern_embed_correlation.py \
            --embed "$OUT_PT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
            2>&1 | tee "$ART/pearson-master-$TAG.log"
        PEARSON_M=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-master-$TAG.log" | head -1 | awk '{print $3}')

        python3 tools/pattern_embed_correlation.py \
            --embed "$OUT_PT" --ref "$V7" --data "$V8_DATA" --n 1000 --seed 17 \
            2>&1 | tee "$ART/pearson-selfplay-$TAG.log"
        PEARSON_S=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-selfplay-$TAG.log" | head -1 | awk '{print $3}')
    fi
    PARAMS=$(grep -oE 'model: [0-9,]+ params' "$ART/train-$TAG.log" | head -1 | awk '{print $2}')
    RESULTS+="  $TAG  params=$PARAMS  train=${TRAIN_SEC}s  pearson_master=$PEARSON_M  pearson_selfplay=$PEARSON_S"$'\n'
done

echo
echo "=========================================================="
echo "       0068 PATTERN EMBED VARIANTS SWEEP VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Baseline 0067 (v2-d4-h64) : pearson master +0.6109"
echo
echo "  Comparaison aux paradigm cousins :"
echo "    0065 (v3 linear)         : pearson master ~0.28"
echo "    0066 (v3 linear + MLP h) : pearson master ~0.12"
echo
echo "  Action :"
echo "    * meilleur pearson master > 0.65  → port C++ avec cette config"
echo "    * plateau ≈ 0.61                  → port C++ baseline 0067"
echo "    * dégradation avec capacité       → overfit, baseline 0067 reste optimal"
echo "=========================================================="
