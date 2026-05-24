#!/usr/bin/env bash
# id: 0046-train-pattern-v2-phase1-tuned
# description: Phase 1 du PATTERN_ROADMAP / ROADMAP.md. Re-train pattern
#              v2 sur le même dataset (depth20-1M.bin, 0010) et avec le
#              même v5 NNUE adversaire que 0025a-7, mais avec toutes les
#              améliorations training Phase 1 :
#                * augmentation symétrie horizontale (×2 data gratuit)
#                * score-scale 0.01 (fix le MSE qui écrase BCE)
#                * lambda 0.5 (mix score+WDL équilibré)
#                * warmup 5% + cosine LR decay
#                * weight decay 1e-5 + grad clip 1.0
#                * multi-seed averaging (3 runs)
#
# Baseline à battre : 0025a-7 → 3/54 vs v5 d6 (rate 0.056), 0/54 vs v5 d10.
# Decision gate (Phase 1 PATTERN_ROADMAP) :
#   rate vs v5 d10 >= 0.20 → archi pattern viable, passer à Phase 2 (self-play loop).
#   rate vs v5 d10 ∈ [0.10, 0.20] → progrès net mais pas suffisant ; explorer
#       Phase 0b (master volume sur le training set) AVANT Phase 2.
#   rate vs v5 d10 < 0.10 → training supervised cheap inadequate. Phase 2 ou
#       abandon de l'axe pattern session.
#
# expected_duration: ~3-4h sur 4 vCPU CCX23 :
#                    * 3 runs train v2 × ~45 min chacun (~2.5h)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0046-train-pattern-v2-phase1-tuned"
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
echo "=== train pattern v2 — Phase 1 (3-seed averaged, mirror aug, scaled MSE) ==="
OUT_JPAT="$ART/pattern-v2-phase1.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --epochs         30 \
    --batch          4096 \
    --lr             1e-2 \
    --lambda         0.5 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --grad-clip      1.0 \
    --warmup-frac    0.05 \
    --cosine-schedule \
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
echo "       0046 PATTERN v2 PHASE 1 VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References (memoires d'avant) :"
echo "    0025a-7 (v2 pure-WDL, no training fixes) : 3/54 vs v5 d6, 0/54 vs v5 d10"
echo "    v5 vs handcrafted (réf absolue)          : 0.852"
echo
echo "  Decision (per PATTERN_ROADMAP §1) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.20) }'; then
    echo "    VIABLE — Phase 1 fixes ont débloqué l'archi pattern."
    echo "    Suite : Phase 2 (self-play loop pattern). Voir PATTERN_ROADMAP §2."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRES NET mais pas suffisant. Combiner avec un meilleur"
    echo "    dataset (master volume, ou quiet-filtered de Phase 0) avant"
    echo "    de passer Phase 2."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.05) }'; then
    echo "    SIGNAL FAIBLE — Phase 1 a aidé marginalement vs 0025a-7."
    echo "    Phase 2 self-play est probablement nécessaire pour franchir"
    echo "    le palier."
else
    echo "    PAS DE PROGRES — training supervised même tuné est inadequate."
    echo "    Décision : Phase 2 self-play (coût €20-40, 3-4 sem) OU"
    echo "    abandon pattern axis pour cette session."
fi
echo "=========================================================="
