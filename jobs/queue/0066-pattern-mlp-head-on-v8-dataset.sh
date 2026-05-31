#!/usr/bin/env bash
# id: 0066-pattern-mlp-head-on-v8-dataset
# description: Test paradigm shift — hybrid pattern + MLP head (JPAT v7).
#              One-shot supervised training sur le DATASET v8 (1M v7-
#              labelled-depth-16 records), pattern v3 + kitchen sink
#              (extras + phase split + mobility) + MLP head H=16.
#
# Hypothèse : 12 hypothèses pattern flat. Toutes utilisaient une eval
# LINÉAIRE des pattern lookups (somme directe). Le MLP head ajoute une
# non-linéarité résiduelle qui pourrait capturer des interactions entre
# patterns que la somme linéaire ne peut pas représenter.
#
# Direct A/B vs 0065 :
#   * 0065 : v3 kitchen sink linéaire → 0/54, pearson 0.28 sur master
#   * 0066 : 0065 + MLP head H=16 (~145 weights, ~600 bytes extra)
#
# Si MLP head améliore le pearson OR le win-rate vs 0065 baseline,
# c'est la première composante qui débloque quelque chose. Sinon, 13
# hypothèses cheap exhaustées — paradigm shift architecture pattern
# n'est pas accessible cheap dans notre infra.
#
# expected_duration: ~2-3h sur 8 vCPU CCX33 :
#                    * load 1M v8 dataset (~5 min)
#                    * 3 seeds × LBFGS train (~30-45 min each)
#                    * bench + pearson (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0066-pattern-mlp-head-on-v8-dataset"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset: $V8_DATA"
echo "MLP head: hidden=16 (~145 weights + ~600 bytes per JPAT)"

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
echo "=== train pattern v3 + kitchen sink + MLP head H=16 on v8 dataset ==="
OUT_JPAT="$ART/pattern-v3-mlp16-on-v8.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$V8_DATA" \
    --out            "$OUT_JPAT" \
    --patterns       v3 \
    --hybrid --extras --phase-split --mobility \
    --mlp-hidden     16 \
    --pattern-base   3 \
    --init-man       100 --init-king 300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         0.7 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --lbfgs-max-iter 20 --lbfgs-history 10 \
    --lbfgs-early-stop-patience 5 \
    --symmetry \
    --num-seeds      3 \
    --seed           42 \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
ls -lh "$OUT_JPAT"

echo
echo "=== bench vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$OUT_JPAT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

echo "=== pearson vs v7 (master positions, neutral sample) ==="
MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw
PEARSON="-"
if [ -f "$MASTER_SAMPLE" ]; then
    python3 tools/pattern_eval_correlation.py \
        --pattern "$OUT_JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
        2>&1 | tee "$ART/pearson-vs-v7.log"
    PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-vs-v7.log" | head -1 | awk '{print $3}')
fi

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0066 MLP HEAD ON V8 DATASET VERDICT"
echo "=========================================================="
echo "  train wall:        ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:    $RATE_HC"
echo "  vs v5 d10:         $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 d10:         $RATE_V6_D10"
echo "  vs v7 d10:         $RATE_V7_D10"
echo "  pearson vs v7 (master positions): $PEARSON"
echo
echo "  Direct A/B :"
echo "    0065 (linear, same dataset) : pearson 0.2797, win-rate 0/54"
echo "    0066 (+ MLP head H=16)      : pearson $PEARSON, win-rate vs v6 = $RATE_V6_D10"
echo
if [ -n "$RATE_V6_D10" ] && awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    MLP HEAD UNLOCK — non-linéarité débloque l'archi pattern."
    echo "    Premier paradigm shift positif de la session. Scale-up."
elif [ -n "$PEARSON" ] && awk -v p="$PEARSON" -v p65=0.2797 \
       'BEGIN { exit !(p - p65 > 0.10) }'; then
    echo "    PEARSON AMÉLIORÉ vs 0065 (linear). MLP head capture des"
    echo "    interactions non-linéaires utiles, mais pas encore assez"
    echo "    pour franchir win-rate. Scale-up volume + self-play."
else
    echo "    FLAT — 13 hypothèses cheap toutes réfutées. MLP head"
    echo "    n'apporte rien non plus. Pattern axis dans notre infra"
    echo "    NÉCESSITE un leverage qualitatif fondamentalement nouveau"
    echo "    (réplication Scan exacte, nouvelle archi paradigm, ou"
    echo "    investment compute >>) pour être relancée."
fi
echo "=========================================================="
