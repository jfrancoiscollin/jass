#!/usr/bin/env bash
# id: 0025a-7-train-pattern-v2-wdl-only
# description: Pattern v2 last-shot — pure WDL BCE training (lambda=0,
#              drop score MSE entièrement). Le diagnostic du run v2
#              précédent (0025a-6) : la loss était dominée par MSE,
#              qui poussait vers prediction=0 (le mean trivial). En
#              retirant MSE et boostant le LR pour compenser le
#              gradient BCE tiny (~1/400 par step), on teste si les
#              patterns peuvent capturer le signal WDL.
#
#              Si ça reste 0/54 : preuve solide que notre training
#              setup ne peut pas faire converger 6M weights sur 1M
#              records, indépendamment de l'archi. Stop l'axe pattern.
#
#              Si ça donne ANY rate >0.05 vs handcrafted : signal,
#              l'archi peut être travaillée. Suite : tuning training.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-7-train-pattern-v2-wdl-only"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

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

echo "=== train v2 pattern net : pure WDL BCE (lambda=0, lr=1.0) ==="
OUT_JPAT="$ART/pattern-v2-wdl.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data     "$DATASET" \
    --out      "$OUT_JPAT" \
    --patterns v2 \
    --epochs   30 \
    --batch    4096 \
    --lr       1.0 \
    --lambda   0.0 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

ls -lh "$OUT_JPAT"

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
echo "       0025a-7 PATTERN v2 PURE-WDL VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
if   awk -v r="$RATE_HC" 'BEGIN { exit !(r > 0.50) }'; then
    echo "  STRONG SIGNAL — patterns peuvent battre handcrafted. L'archi"
    echo "  est viable, le bug était le training MSE-dominated. Suite :"
    echo "  re-tuner train_pattern.py avec ce setup, scale-up."
elif awk -v r="$RATE_HC" 'BEGIN { exit !(r > 0.10) }'; then
    echo "  SIGNAL FAIBLE — patterns capturent quelque chose mais pas"
    echo "  beaucoup. Plus de training, plus de patterns, ou hyper"
    echo "  param tweaks. Encore une carte à jouer."
else
    echo "  PAS DE SIGNAL — notre training setup ne peut pas faire"
    echo "  converger ce modèle. Stop l'axe pattern pour cette session."
fi
echo "=========================================================="
