#!/usr/bin/env bash
# id: 0051-g1-lbfgs-d1-hybrid
# description: G1 du docs/archives/SCAN_METHODOLOGY_GAP.md. Re-train pattern v2
#              hybrid base-5 (recipe D1 = 0048) SUR LE MÊME dataset
#              (depth20-1M.bin de 0010), MAIS avec L-BFGS full-batch
#              au lieu d'Adam minibatch.
#
# Hypothèse testée : la loss `λ·MSE + (1-λ)·BCE` est convexe en pattern
# weights. Adam sur minibatches oscillerait autour du minimum tandis que
# LBFGS strong-Wolfe converge en dizaines d'itérations full-batch. Si
# l'optimisation était le bottleneck de 0048 (val_mse stable à 91.87M
# = optimum local du minibatch SGD), LBFGS devrait trouver un meilleur
# minimum.
#
# Safeguards (cf. smoke test sur master data qui a montré overfit
# sévère LBFGS sans régularisation) :
#   * weight_decay 1e-5 appliqué comme L2 manuel dans le closure
#   * early stopping patience 5 (best-val checkpoint restoré)
#   * lbfgs_max_iter 20 par outer step (~600 inner iters total)
#
# Decision gate (per docs/archives/SCAN_METHODOLOGY_GAP.md §G1) :
#   rate vs v5 d10 ≥ 0.10 → Adam était en cause, continuer G2 (distillation)
#                          avec LBFGS comme optimizer default pattern.
#   ∈ (0.05, 0.10)        → progrès marginal, LBFGS pas décisif, faire G2
#                          quand même pour borner l'hypothèse archi.
#   ≤ 0.05                → Adam n'était pas le bottleneck. La piste
#                          optimisation est exhaustée. Pivot G2 ou G3
#                          (feature engineering) avec garde-fou strict.
#
# expected_duration: ~1-2h sur 4 vCPU CCX23 :
#                    * 3 seeds × LBFGS 30 outer iters (early stop possible)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0051-g1-lbfgs-d1-hybrid"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "dataset: $DATASET ($(stat -c %s "$DATASET") bytes)"
echo "v5 ref:  $V5"

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
echo "=== train pattern v2 HYBRID base-5 — G1 (L-BFGS full-batch) ==="
OUT_JPAT="$ART/pattern-v2-g1-lbfgs.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
    --init-man       100 \
    --init-king      300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         0.5 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --grad-clip      0 \
    --lbfgs-max-iter 20 \
    --lbfgs-history  10 \
    --lbfgs-early-stop-patience 5 \
    --symmetry \
    --num-seeds      3 \
    --seed           42 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

ls -lh "$OUT_JPAT"

echo
echo "=== bench vs handcrafted (depth 6) ==="
./build/jass --benchmark-nnue "$OUT_JPAT" 2>&1 | tee "$ART/bench-vs-hc.log"
echo "=== bench vs v5 (depth 6) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
echo "=== bench vs v5 (depth 10) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0051 G1 PATTERN v2 HYBRID + L-BFGS VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References (Adam paths) :"
echo "    0046 Phase 1 pure pattern   : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0048 D1 hybrid base-5 Adam  : 0/18 hc, 6/54 d6, 0/54 d10"
echo "    0049 D2 hybrid base-3 Adam  : 0/18 hc, 1.5/54 d6, 0/54 d10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §G1) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    ADAM WAS THE BOTTLENECK — LBFGS débloque significativement."
    echo "    Suite : G2 (distillation depuis v6) avec LBFGS comme default."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.05) }'; then
    echo "    PROGRÈS MARGINAL — LBFGS pas décisif, mais a aidé un peu."
    echo "    Faire G2 quand même pour valider l'hypothèse archi."
else
    echo "    NOT THE BOTTLENECK — Adam n'était pas en cause. Le problème"
    echo "    est ailleurs (probablement labels score bruités). Pivot G2"
    echo "    (distillation depuis v6 = labels propres) avec garde-fou"
    echo "    strict : si G2 ne décolle pas non plus, abandon pattern axis."
fi
echo "=========================================================="
