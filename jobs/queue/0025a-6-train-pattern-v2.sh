#!/usr/bin/env bash
# id: 0025a-6-train-pattern-v2
# description: Pattern v2 (Scan-class) : 16 patterns × 8 squares,
#              6.25M weights, full coverage 50/50 squares avec
#              overlap. 30× plus de params que v1 et coverage
#              complète — c'est l'archi pattern à la bonne échelle
#              pour vraiment tester l'hypothèse.
#
#              Entrainé sur 0010 1M (depth-20 Linear-labelled).
#              Bench head-to-head vs v5 à depth 6 et 10.
#
#              Décision :
#                rate_d10 > 0.55 → patterns gagnent ; archi confirmée.
#                rate_d10 ≈ 0.50 → tie. Patterns équivalents au MLP.
#                rate_d10 < 0.45 → patterns régressent. L'hypothèse
#                                  archi est invalidée pour jass au
#                                  moins à cette échelle.
#
# expected_duration: ~30-90 min sur 4 vCPU CCX23. Training plus lent
#                    que v1 (16 tables × 5^8 lookups) mais reste cheap
#                    grâce au sparse update. Quant + bench rapides.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-6-train-pattern-v2"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

echo "=== rebuilding jass ==="
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

echo "=== train v2 pattern net (16×8, full coverage) ==="
OUT_JPAT="$ART/pattern-v2.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data     "$DATASET" \
    --out      "$OUT_JPAT" \
    --patterns v2 \
    --epochs   30 \
    --batch    4096 \
    --lr       5e-3 \
    --lambda   0.5 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

ls -lh "$OUT_JPAT"

echo "=== bench v2 pattern vs handcrafted (depth 6) ==="
./build/jass --benchmark-nnue "$OUT_JPAT" 2>&1 | tee "$ART/bench-vs-hc.log"

echo "=== bench v2 pattern vs v5 (depth 6, 3 pairs) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 6 3 \
    2>&1 | tee "$ART/bench-vs-v5-d6.log"

echo "=== bench v2 pattern vs v5 (depth 10, 3 pairs) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 10 3 \
    2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0025a-6 PATTERN v2 (16×8, full coverage) VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s"
echo "  weights:              6.25M (vs ~150K for MLPNetworkQ 256-128)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References :"
echo "    v5 (256-128 MLP) vs handcrafted: 0.852 / +304 ELO"
echo "    Pattern v1 vs v5 d10: 0.000 (5000 weights, sous-paramétré)"
echo
echo "  Decision:"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    PATTERNS GAGNENT — l'hypothèse archi est validée."
    echo "    Direction confirmée : itérer sur le pattern set + scale up."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    TIE — patterns équivalents au MLP. Bonus : ~285× faster"
    echo "    eval (lookup vs matmul). Choix archi non-trivial."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.40) }'; then
    echo "    LÉGER LOSS — patterns proches mais derrière. Probable"
    echo "    fix : pattern set plus large (24, 32 patterns), training"
    echo "    plus long, ou hyperparams revus."
else
    echo "    PATTERNS REGRESSENT — l'hypothèse archi est invalidée"
    echo "    pour jass à cette échelle. v5 (MLP) reste l'archi de"
    echo "    référence. Plus de cycles patterns sans hypothèse forte."
fi
echo "=========================================================="
