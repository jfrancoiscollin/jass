#!/usr/bin/env bash
# id: 0070-pattern-embed-variants-vs-v6
# description: Paradigm shift (A) — 3 retrain variants pour tester
#              les hypothèses "ce que 0067 a raté" :
#
#   V1 (clean POV)     : same as 0067 + --no-stm-flip
#                        (cleaner skeleton convention — modèle 0067
#                        avait mat_diff dans un référentiel mixte)
#   V2 (long train)    : V1 + epochs 100 (vs 30) — val_mse de 0067
#                        encore en descente à epoch 30
#   V3 (low lambda)    : V1 + lambda 0.3 (vs 0.7) — donne plus de poids
#                        au WDL BCE, devrait calmer l'amplitude eval
#                        (0067 avait std 1.46× plus grand que v7)
#
# Chaque variante : train + export JPAT v8 + bench vs v5/v6 d10 (1 seed
# × 18 games chacun = 36 games par variante). Plus le pearson vs v7
# sur master positions pour cross-check qualitatif.
#
# Decision gate :
#   * meilleure variante > 6/18 (~33%) vs v6 d10 → signal réel, scale-up
#     (3 seeds × 18 games × autres adversaires pour formaliser)
#   * meilleure variante ≤ 2/18 (~11%) → bruit ; paradigm shift A
#     définitivement réfuté ; pivot (B) MLPNetworkQ enrichi ou
#     (D) AlphaZero MCTS
#   * meilleure variante 3-5/18 → ambiguë, scale-up sur cette variante
#     pour disambiguer
#
# expected_duration: ~1.5-2h sur 8 vCPU CCX33 :
#                    * 3 variantes × (~5-15 min train + 5 min bench + 1 min pearson)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0070-pattern-embed-variants-vs-v6"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V6" ] && [ -f "$V6" ] || { echo "ABORT: v6 NNUE not found"; exit 3; }

MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset    : $V8_DATA"
echo "v5/v6/v7      : $V5 / $V6 / $V7"

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

# Variant configs : tag, extra train args
CONFIGS=(
    "V1-cleanPOV       --no-stm-flip --epochs  30 --lambda 0.7"
    "V2-cleanPOV-100ep --no-stm-flip --epochs 100 --lambda 0.7"
    "V3-cleanPOV-lam03 --no-stm-flip --epochs  30 --lambda 0.3"
)

RESULTS=""
for entry in "${CONFIGS[@]}"; do
    TAG=$(echo "$entry" | awk '{print $1}')
    EXTRA=$(echo "$entry" | cut -d' ' -f2-)
    OUT_PT="$ART/embed-$TAG.pt"
    OUT_JPAT="$ART/embed-$TAG.jpat"

    echo
    echo "=========================================================="
    echo "=== TRAIN $TAG ==="
    echo "    args: $EXTRA"
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern_embed.py \
        --data "$V8_DATA" --out "$OUT_PT" \
        --patterns v2 --embed-dim 4 --mlp-hidden 64 \
        --batch 4096 --lr 1e-3 --score-scale 0.01 \
        --weight-decay 1e-5 --val-frac 0.05 --seed 42 \
        $EXTRA \
        2>&1 | tee "$ART/train-$TAG.log"
    TRAIN_SEC=$(( $(date +%s) - START ))

    python3 tools/embed_pt_to_jpat.py --in "$OUT_PT" --out "$OUT_JPAT" \
        2>&1 | tee "$ART/export-$TAG.log"

    echo
    echo "=== BENCH $TAG vs v6 d10 ==="
    ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V6" 10 1 \
        2>&1 | tee "$ART/bench-vs-v6-$TAG.log"
    RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-$TAG.log" | head -1 | awk '{print $3}')

    echo
    echo "=== BENCH $TAG vs v5 d10 ==="
    ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 10 1 \
        2>&1 | tee "$ART/bench-vs-v5-$TAG.log"
    RATE_V5=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-$TAG.log" | head -1 | awk '{print $3}')

    echo
    echo "=== PEARSON $TAG vs v7 (master neutre) ==="
    python3 tools/pattern_embed_correlation.py \
        --embed "$OUT_PT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
        2>&1 | tee "$ART/pearson-$TAG.log"
    PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-$TAG.log" | head -1 | awk '{print $3}')

    RESULTS+="  $TAG  train=${TRAIN_SEC}s  pearson=$PEARSON  vs_v6=$RATE_V6  vs_v5=$RATE_V5"$'\n'
done

echo
echo "=========================================================="
echo "       0070 EMBED VARIANTS vs v6 VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Baseline 0067 (legacy POV, 30 ep, lambda 0.7) :"
echo "    pearson master = 0.6109  vs v6 d10 = 0/18  vs v5 d10 = 0/18"
echo
echo "  Action :"
echo "    * meilleur vs v6 > 6/18 (~33%) → signal réel, scale-up à 3 seeds"
echo "    * meilleur vs v6 ≤ 2/18 (~11%) → bruit, paradigm A réfuté définitivement,"
echo "                                     pivot (B) MLPNetworkQ enrichi ou (D) AlphaZero"
echo "    * meilleur vs v6 entre 3-5/18 → ambiguë, scale-up cette variante"
echo "=========================================================="
