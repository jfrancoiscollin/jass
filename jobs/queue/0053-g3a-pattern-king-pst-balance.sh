#!/usr/bin/env bash
# id: 0053-g3a-pattern-king-pst-balance
# description: G3a du docs/archives/SCAN_METHODOLOGY_GAP.md (révision 2026-05-28).
#              Re-train pattern v2 hybrid base-3 sur le même dataset que
#              0048 (depth20-1M.bin), avec en plus le squelette Scan-aligned
#              **complet** (modulo phase split MG/EG qui est G3b) :
#                * king_pst[50] : per-square king positional bonus, white-POV
#                  (black kings use row-mirror pst[50-s])
#                * balance scalar : L/R skew penalty
#
# Hypothèse testée : G1 (LBFGS) et G2 (distillation v7) ont confirmé que
# ni l'optimiseur ni la qualité des labels ne débloquent l'archi pattern
# v2 (hybrid skeleton 2 scalaires). Le diagnostic restant : **feature
# engineering insuffisant**. Notre D1 hybrid avait juste man_value +
# king_value scalaires ; Scan a en plus 50 weights de PST king + balance
# + mobility (skip mobility pour G3a, coût eval trop élevé). G3a ajoute
# 51 nouveaux poids structurels (50 PST + 1 balance) au modèle.
#
# Choix base-3 (pas base-5) : aligné Scan, orthogonal au PST (sinon
# double-counting king info entre patterns et PST), et 60× plus dense
# en buckets.
#
# Decision gate (per §G3) :
#   rate vs v5 d10 ≥ 0.30 → archi viable, on a la baseline pour G4 self-play.
#   ∈ [0.10, 0.30]        → progrès net, considérer G3b (phase split MG/EG)
#                          ou G4 quand même.
#   < 0.10                → feature engineering n'est PAS le facteur
#                          dominant ; les 51 weights extras + PST mirror
#                          n'ont pas débloqué. Reste G4 (self-play TD-leaf
#                          €20-40, risquée) ou abandon honest.
#
# expected_duration: ~3-4h sur 4 vCPU CCX23 :
#                    * 3 seeds × LBFGS ~30 min (early stop possible)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0053-g3a-pattern-king-pst-balance"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "dataset: $DATASET ($(stat -c %s "$DATASET") bytes)"
echo "v5 ref: $V5"
echo "v6 ref: ${V6:-<missing>}"
echo "v7 ref: ${V7:-<missing>}"

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
echo "=== train pattern v2 HYBRID base-3 + king PST + balance — G3a ==="
OUT_JPAT="$ART/pattern-v2-g3a.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
    --extras \
    --pattern-base   3 \
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
echo "=== bench vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$OUT_JPAT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
if [ -n "$V6" ]; then
  ./build/jass --benchmark-nnue-vs-nnue    "$OUT_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
fi
if [ -n "$V7" ]; then
  ./build/jass --benchmark-nnue-vs-nnue    "$OUT_JPAT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"
fi

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""
RATE_V7_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
[ -f "$ART/bench-vs-v7-d10.log" ] && RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0053 G3a PATTERN v2 + king PST + balance VERDICT"
echo "=========================================================="
echo "  train wall:        ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:    $RATE_HC"
echo "  vs v5 d6 / d10:    $RATE_V5_D6 / $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 d10:         $RATE_V6_D10"
[ -n "$RATE_V7_D10" ] && echo "  vs v7 d10:         $RATE_V7_D10"
echo
echo "  References (pattern v2 supervised paths) :"
echo "    0048 D1 hybrid base-5 Adam   : 0/18 hc, 6/54 d6, 0/54 d10"
echo "    0049 D2 hybrid base-3 Adam   : 0/18 hc, 1.5/54 d6, 0/54 d10"
echo "    0051 G1 LBFGS base-5         : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0052 G2 distill v7 base-5    : 0/18 hc, 0/54 d6, 0/54 d10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §G3) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.30) }'; then
    echo "    FEATURE ENGINEERING WAS THE BOTTLENECK — archi pattern viable."
    echo "    On a maintenant une baseline saine pour G4 (self-play TD-leaf)."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRÈS NET — feature engineering aide. Considérer G3b (phase"
    echo "    split MG/EG) qui Scan utilise aussi, avant G4."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.05) }'; then
    echo "    PROGRÈS MARGINAL — king PST + balance ajoutent un peu mais"
    echo "    pas suffisant. G3b phase split à essayer ou abandon."
else
    echo "    FLAT — même feature engineering complet n'est pas la racine."
    echo "    Reste G4 self-play TD-leaf (€20-40, 3-4 sem, risqué) ou"
    echo "    abandon honest de l'axe pattern pour cette session."
fi
echo "=========================================================="
