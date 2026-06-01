#!/usr/bin/env bash
# id: 0077-scan-distill-pattern-v3
# description: Distillation Scan vers archi PATTERN (V3 base-3) au lieu
#              de MLP. Si MLP distillation (0073-0076) plafonne par
#              mismatch architectural (universal approximation hard sur
#              une cible naturellement pattern-shaped), pattern eval
#              doit converger directement.
#
# Function class match : Scan = somme de pattern lookups, V3 patterns
# base-3 = même structure (~4.25M weights, capacité aligned avec Scan).
# Nos 15 hypothèses pattern précédentes ont toutes utilisé des labels
# v7/v8/master = pas Scan-quality. Distillation Scan = première vraie
# cible représentée naturellement par patterns.
#
# Réutilise dataset distillé 100K (de 0073-0076). LBFGS + lambda 1.0
# (pure score MSE), pas de WDL blend, pas de master (cohérent avec
# 0075 pure distillation MLP).
#
# Decision gate :
#   * pearson v10p vs Scan (sur master) > 0.80 → pattern + Scan unlock,
#     scale-up 1M @ d12 puis distill (0078)
#   * vs Scan d10 > 0.10 → signal qualitatif, scale-up
#   * vs v8 d10 > 0.50 → ship comme v10-pattern
#   * tout < seuil + 0076 MLP aussi flat → infra alpha-beta jass ne peut
#     pas exploiter Scan-quality eval, pivot (D) ou drop
#
# expected_duration: ~15-25 min (LBFGS sur 100K + bench)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0077-scan-distill-pattern-v3"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER_SAMPLE=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)
[ -n "$MASTER_SAMPLE" ] && [ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw 2>/dev/null | head -1)

for CANDIDATE in \
    /root/jass/jobs/results/0076-scan-distill-256-128-pure/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0075-scan-distillation-pure-no-master/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0074-scan-distillation-pilot-master-bce-fix/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0073-scan-distillation-pilot/artefacts.src/v10-distilled-100K.bin
do
    if [ -f "$CANDIDATE" ]; then
        RELAB_SRC="$CANDIDATE"
        break
    fi
done
[ -n "${RELAB_SRC:-}" ] || { echo "ABORT: no distilled dataset found"; exit 3; }

RELAB="$ART/v10-distilled-100K.bin"
cp "$RELAB_SRC" "$RELAB"
echo "Using distilled dataset : $RELAB_SRC"

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

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

# Train pattern V3 base-3 hybrid (skeleton + patterns) via LBFGS pure MSE
# on the Scan-distilled dataset. ~4.25M weights, function class matches
# Scan's eval structure.
echo
echo "=========================================================="
echo "=== train pattern V3 base-3 LBFGS pure MSE sur distilled ==="
echo "=========================================================="
OUT_JPAT="$ART/pattern-v3-scan-distilled.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$RELAB" \
    --out            "$OUT_JPAT" \
    --patterns       v3 \
    --hybrid \
    --pattern-base   3 \
    --init-man       100 --init-king 300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         1.0 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --lbfgs-max-iter 20 --lbfgs-history 10 \
    --lbfgs-early-stop-patience 5 \
    --symmetry \
    --num-seeds      1 \
    --seed           42 \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
ls -lh "$OUT_JPAT"

# --- Bench ---
echo
echo "=========================================================="
echo "=== bench pattern v3 distilled vs Scan / v6 / v7 / v8 d10 ==="
echo "=========================================================="

python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$OUT_JPAT" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
RATE_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
RATE_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
RATE_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

# Pearson vs Scan eval directly (would need Scan as labeller — skip,
# use vs v7 NNUE proxy via pattern_eval_correlation if available).
PEARSON="-"
if [ -f "$MASTER_SAMPLE" ] && [ -n "$V7" ]; then
    python3 tools/pattern_eval_correlation.py \
        --pattern "$OUT_JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
        2>&1 | tee "$ART/pearson-vs-v7.log"
    PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-vs-v7.log" | head -1 | awk '{print $3}')
fi

echo
echo "=========================================================="
echo "       0077 SCAN DISTILL → PATTERN V3 VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s"
echo "  vs Scan d10 : $RATE_SCAN"
echo "  vs v6 d10   : $RATE_V6"
echo "  vs v7 d10   : $RATE_V7"
echo "  vs v8 d10   : $RATE_V8"
echo "  pearson v10p vs v7 (master) : $PEARSON"
echo
echo "  Comparaison cross-archi (même 100K distilled) :"
echo "    0075 MLP 512-256 pure  : vs Scan 0.000  vs v8 0.111"
echo "    0076 MLP 256-128 pure  : (à comparer post-0076 finalize)"
echo "    0077 PATTERN v3 base-3 : vs Scan $RATE_SCAN  vs v8 $RATE_V8"
echo
echo "  Decision :"
echo "    * v10p vs v8 > 0.50 → PATTERN distill unlock — scale-up 1M (0078)"
echo "    * vs Scan > 0.10    → signal qualitatif vs MLP flat"
echo "    * tout < seuil + 0076 MLP aussi flat → infra alpha-beta jass ne"
echo "      peut pas exploiter Scan-quality eval. Pivot (D) ou drop."
echo "=========================================================="
