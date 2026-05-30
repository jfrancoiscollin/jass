#!/usr/bin/env bash
# id: 0065-pattern-train-on-v8-dataset
# description: TD-leaf-equivalent test : train pattern v3 kitchen sink
#              sur le DATASET v8 (1M records labellés par v7 à depth
#              16). Pas de self-play loop — pure supervised one-shot
#              avec score MSE + WDL BCE blend.
#
# Hypothèse : 0061 (bootstrap supervised sur master WDL) avait pearson
# 0.34 vs v7 sur master positions. Les labels score depth-16 du v8
# dataset sont **beaucoup plus précis** que WDL outcome. Trainer sur ces
# labels devrait produire un pattern proche de v7 (search-aware) plutôt
# que proche de master WDL (outcome-noisy). C'est l'équivalent de TD-
# leaf (la valeur PV-leaf est utilisée comme label).
#
# Différence avec G2 distillation : G2 utilisait `v7.evaluate(pos)`
# STATIC eval. Ici on utilise `v7.search(pos, depth=16)` → vraies
# valeurs minimax, pas juste eval feedforward.
#
# Setup :
#   * Pattern v3 hybrid + extras + phase split + mobility (kitchen sink)
#   * Dataset : 0056 v8 (1M, v7 labeller, depth 16, quiet+pv-extract)
#   * Loss : lambda=0.7 (70% score MSE + 30% WDL BCE) — score labels
#     sont de qualité, on les utilise.
#   * 3 seeds, LBFGS, symmetry aug
#
# Decision gate :
#   rate vs v6 d10 ≥ 0.10 → TD-leaf labels were the key → suite : self-
#                          play loop bootstrapped from this pattern.
#   < 0.10                → pattern arch fundamentalement incapable de
#                          représenter v7-quality even with best labels.
#
# expected_duration: ~2-3h sur 8 vCPU CCX33 :
#                    * load 1M v8 dataset + extract features (~5-10 min)
#                    * 3 seeds × LBFGS (~30-45 min each)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0065-pattern-train-on-v8-dataset"
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
echo "v8 dataset: $V8_DATA ($(stat -c %s "$V8_DATA") bytes)"

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
echo "=== train pattern v3 kitchen sink on v8 dataset (TD-leaf labels) ==="
OUT_JPAT="$ART/pattern-v3-on-v8.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$V8_DATA" \
    --out            "$OUT_JPAT" \
    --patterns       v3 \
    --hybrid --extras --phase-split --mobility \
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
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

echo "=== pearson vs v7 (n=1000) on master sample (neutral) ==="
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
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0065 PATTERN ON V8 DATASET (TD-leaf labels) VERDICT"
echo "=========================================================="
echo "  train wall:        ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:    $RATE_HC"
echo "  vs v5 d6 / d10:    $RATE_V5_D6 / $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 d10:         $RATE_V6_D10"
echo "  vs v7 d10:         $RATE_V7_D10"
echo "  pearson vs v7 (master positions): $PEARSON"
echo
echo "  Comparaison pearson (neutral master positions) :"
echo "    0061 bootstrap master WDL : 0.34"
echo "    0065 v8 search-depth-16   : $PEARSON"
echo
if [ -n "$RATE_V6_D10" ] && awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    TD-LEAF LABELS UNLOCK — search-quality labels suffisent."
    echo "    Suite : self-play loop bootstrapped from this pattern."
else
    echo "    FLAT — même avec labels search-quality d16, pattern v3"
    echo "    n'arrive pas à représenter une eval compétitive."
fi
echo "=========================================================="
