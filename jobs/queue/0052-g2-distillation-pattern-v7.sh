#!/usr/bin/env bash
# id: 0052-g2-distillation-pattern-v7
# description: G2 du docs/archives/SCAN_METHODOLOGY_GAP.md. Teste si l'archi
#              pattern peut imiter une eval qui marche (v7), en remplaçant
#              les labels score depth-20 bruités par des labels propres =
#              `v7.evaluate(pos)` (knowledge distillation).
#
# Hypothèse testée : G1 (0051) a montré que LBFGS converge vers le vrai
# minimum de la loss, mais ce minimum est `pred ≈ 0` parce que les labels
# score sont trop bruités (depth-20 search sur self-play). Si on remplace
# les labels par les sorties d'un réseau qui marche (v7), patterns
# devraient pouvoir l'imiter — c'est ce que la régression linéaire fait
# trivialement sur des targets bien définies.
#
# Decision gate (per §G2) :
#   rate vs v6 d10 ≥ 0.40 → archi peut représenter une eval. Le label
#                          était LE bottleneck. Suite G3 (feature engineering
#                          complet : mg/eg, king PST, mobility).
#   ∈ [0.20, 0.40]        → archi limitée, partial signal. Décision difficile :
#                          G3 risquée vs accepter le plateau.
#   < 0.20                → archi pattern fondamentalement inadaptée même
#                          sur labels propres. Abandon HONNÊTE pattern axis.
#
# expected_duration: ~2h sur 4 vCPU CCX23 :
#                    * rewrite scores v7 sur 1M records (~1 min, evaluate fast)
#                    * 3 seeds × LBFGS (~30 min chaque, early stop possible)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0052-g2-distillation-pattern-v7"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Source dataset : 1M depth-20 self-play (0010). v7 outputs replace its
# score labels.
SRC_DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
DISTILLED_DATASET="$ART/depth20-1M-distilled-v7.bin"

V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$SRC_DATASET" ] || { echo "ABORT: $SRC_DATASET not found"; exit 3; }
[ -n "$V7" ] && [ -f "$V7" ] || { echo "ABORT: v7 NNUE not found"; exit 3; }
[ -n "$V6" ] && [ -f "$V6" ] || { echo "ABORT: v6 NNUE not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v7 labeller:    $V7"
echo "v6 bench ref:   $V6"
echo "v5 bench ref:   $V5"
echo "src dataset:    $SRC_DATASET"

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
echo "=== Phase G2a : distill 1M dataset via v7 evaluate ==="
START_DIST=$(date +%s)
./build/jass --rewrite-scores-with-nnue "$SRC_DATASET" "$DISTILLED_DATASET" \
    --nnue "$V7" 2>&1 | tee "$ART/distill.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: distill failed"; exit 4; }
DIST_SEC=$(( $(date +%s) - START_DIST ))
ls -lh "$DISTILLED_DATASET"

echo
echo "=== Phase G2b : train pattern v2 HYBRID + L-BFGS on distilled labels ==="
OUT_JPAT="$ART/pattern-v2-g2-distilled.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DISTILLED_DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
    --init-man       100 \
    --init-king      300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         0.9 \
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
echo "=== Phase G2c : bench pattern vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$OUT_JPAT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V6"  6 3 2>&1 | tee "$ART/bench-vs-v6-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V7"  6 3 2>&1 | tee "$ART/bench-vs-v7-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"      | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"   | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log"  | head -1 | awk '{print $3}')
RATE_V6_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d6.log"   | head -1 | awk '{print $3}')
RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log"  | head -1 | awk '{print $3}')
RATE_V7_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d6.log"   | head -1 | awk '{print $3}')
RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log"  | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0052 G2 PATTERN v2 HYBRID DISTILLED FROM v7 VERDICT"
echo "=========================================================="
echo "  distill wall:         ${DIST_SEC}s"
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5  (d6 / d10):    $RATE_V5_D6 / $RATE_V5_D10"
echo "  vs v6  (d6 / d10):    $RATE_V6_D6 / $RATE_V6_D10"
echo "  vs v7  (d6 / d10):    $RATE_V7_D6 / $RATE_V7_D10"
echo
echo "  References (pattern v2 supervised paths) :"
echo "    0048 D1 hybrid base-5 Adam (score labels)  : 0/18 hc, 6/54 d6, 0/54 d10"
echo "    0051 G1 LBFGS (score labels)               : 0/18 hc, 0/54 d6, 0/54 d10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §G2) :"
if   awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.40) }'; then
    echo "    LABEL WAS THE BOTTLENECK — patterns peuvent représenter une"
    echo "    eval qui marche. Suite G3 (feature engineering complet :"
    echo "    mg/eg phase split + king PST + mobility)."
elif awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.20) }'; then
    echo "    PARTIAL SIGNAL — archi pattern peut représenter une eval mais"
    echo "    avec un floor de qualité. G3 risquée ; alternative : accepter"
    echo "    le plateau ~0.30 vs v6 et focus axe data v8 (2M+)."
else
    echo "    ARCHI LIMITÉE même sur labels propres. Pattern v2 (16×8 squares)"
    echo "    ne peut pas représenter une eval forte. Conclusion honnête :"
    echo "    abandon pattern axis pour cette session (le gap n'est pas"
    echo "    fermable cheap, voir G5)."
fi
echo "=========================================================="
