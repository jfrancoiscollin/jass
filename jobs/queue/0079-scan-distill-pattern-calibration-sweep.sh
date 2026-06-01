#!/usr/bin/env bash
# id: 0079-scan-distill-pattern-calibration-sweep
# description: Diagnostic pattern distillation. 0077 a sorti pearson 0.39
#              mais 0/54 partout, std eval 3× compressé. Cause identifiée :
#              --score-scale 0.01 + --lambda 1.0 fait loss = MSE × 1e-4 →
#              LBFGS croit avoir convergé en 1-2 itérations (12s wall).
#              Le pearson 0.39 montre qu'il Y A du signal — juste mal exploité.
#
# Sweep de 4 variantes (sur 100K Scan-distilled, V3 base-3 hybrid) :
#   V1 : Adam     score-scale=0.01 lambda=1.0  (default tooling, baseline)
#   V2 : Adam     score-scale=1.0  lambda=1.0  (no compression, pure MSE)
#   V3 : LBFGS    score-scale=1.0  lambda=1.0  (no compression + LBFGS)
#   V4 : LBFGS    score-scale=0.01 lambda=0.7  (default mode, control)
#
# Si V2 ou V3 sort vs v8 > 0.30, calibration était le bug. Scale-up à 1M
# dans 0080.
# Si tout reste flat, pattern distillation paradigm = vraiment mort.
#
# expected_duration: ~30-45 min total (4 variantes × ~5-10 min train + bench)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0079-scan-distill-pattern-calibration-sweep"
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
    /root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin \
    /root/jass/jobs/results/0076-scan-distill-256-128-pure/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0075-scan-distillation-pure-no-master/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0073-scan-distillation-pilot/artefacts.src/v10-distilled-100K.bin
do
    if [ -f "$CANDIDATE" ]; then
        RELAB_SRC="$CANDIDATE"
        break
    fi
done
[ -n "${RELAB_SRC:-}" ] || { echo "ABORT: no distilled dataset found"; exit 3; }

RELAB="$ART/v10-distilled.bin"
cp "$RELAB_SRC" "$RELAB"
echo "Using distilled dataset : $RELAB_SRC"

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"

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

# Configs : tag : args
CONFIGS=(
    "V1-Adam-s001-l10:--optimizer adam  --epochs 60 --lr 1e-3 --lambda 1.0 --score-scale 0.01"
    "V2-Adam-s100-l10:--optimizer adam  --epochs 60 --lr 1e-3 --lambda 1.0 --score-scale 1.0"
    "V3-LBFGS-s100-l10:--optimizer lbfgs --epochs 30 --lr 1.0  --lambda 1.0 --score-scale 1.0 --lbfgs-max-iter 30 --lbfgs-history 20"
    "V4-LBFGS-s001-l07:--optimizer lbfgs --epochs 30 --lr 1.0  --lambda 0.7 --score-scale 0.01 --lbfgs-max-iter 20 --lbfgs-history 10"
)

RESULTS=""
for entry in "${CONFIGS[@]}"; do
    TAG="${entry%%:*}"
    EXTRA="${entry#*:}"
    JPAT="$ART/pattern-v3-$TAG.jpat"

    echo
    echo "=========================================================="
    echo "=== $TAG ==="
    echo "    $EXTRA"
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern.py \
        --data           "$RELAB" \
        --out            "$JPAT" \
        --patterns       v3 \
        --hybrid \
        --pattern-base   3 \
        --init-man       100 --init-king 300 \
        --weight-decay   1e-5 \
        --symmetry \
        --num-seeds      1 \
        --seed           42 \
        $EXTRA \
        2>&1 | tee "$ART/train-$TAG.log"
    T_SEC=$(( $(date +%s) - START ))

    # Quick pearson vs v7 (master) for qualitative signal.
    PEARSON="-"
    if [ -f "$MASTER_SAMPLE" ] && [ -n "$V7" ]; then
        python3 tools/pattern_eval_correlation.py \
            --pattern "$JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 500 \
            2>&1 | tee "$ART/pearson-$TAG.log"
        PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-$TAG.log" | head -1 | awk '{print $3}')
    fi

    # Quick bench vs v8 only (cheapest signal vs strongest jass baseline).
    R_V8="-"
    if [ -n "$V8" ]; then
        ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V8" 10 1 1 0 \
            2>&1 | tee "$ART/bench-$TAG-vs-v8.log"
        R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$TAG-vs-v8.log" 2>/dev/null | head -1 | awk '{print $3}')
    fi

    RESULTS+="  $TAG  train=${T_SEC}s  pearson=$PEARSON  vs_v8=$R_V8"$'\n'
done

# Pick best variant by pearson AND vs_v8, run full bench.
BEST_TAG=$(python3 - <<EOF
import re
results = """$RESULTS"""
best_score = -2
best_tag = ""
for line in results.strip().split("\n"):
    m = re.match(r"\s*(\S+)\s+train=\S+\s+pearson=([-+0-9.]+|-)\s+vs_v8=([0-9.]+|-)", line)
    if not m: continue
    tag, p, v = m.groups()
    p_val = float(p) if p != "-" else -1
    v_val = float(v) if v != "-" else -1
    # Score = vs_v8 dominant, pearson tiebreaker
    score = v_val * 10 + p_val
    if score > best_score:
        best_score = score
        best_tag = tag
print(best_tag)
EOF
)

echo
echo "=== Full bench best variant : $BEST_TAG ==="
BEST_JPAT="$ART/pattern-v3-${BEST_TAG}.jpat"
if [ -f "$BEST_JPAT" ]; then
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$BEST_JPAT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-best-vs-scan-d10.log"
    BEST_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-best-vs-scan-d10.log" | head -1 | awk '{print $3}')

    [ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$BEST_JPAT" "$V6" 10 3 1 0 \
        2>&1 | tee "$ART/bench-best-vs-v6.log"
    BEST_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-best-vs-v6.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$BEST_JPAT" "$V7" 10 3 1 0 \
        2>&1 | tee "$ART/bench-best-vs-v7.log"
    BEST_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-best-vs-v7.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$BEST_JPAT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-best-vs-v8.log"
    BEST_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-best-vs-v8.log" 2>/dev/null | head -1 | awk '{print $3}')
fi

echo
echo "=========================================================="
echo "       0079 PATTERN CALIBRATION SWEEP VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Best variant : $BEST_TAG"
echo "    full bench vs Scan d10 : ${BEST_SCAN:-?}"
echo "    full bench vs v6 d10   : ${BEST_V6:-?}"
echo "    full bench vs v7 d10   : ${BEST_V7:-?}"
echo "    full bench vs v8 d10   : ${BEST_V8:-?}"
echo
echo "  Reference :"
echo "    0076 MLP 256-128 (100K) : vs Scan 0.056  vs v8 0.167"
echo "    0077 PATTERN V3 (default args) : vs Scan 0.000  vs v8 0.000  pearson 0.39"
echo
echo "  Decision :"
echo "    * best vs v8 > 0.30 → calibration était le bug, scale-up 1M (0080)"
echo "    * pearson > 0.60 mais vs v8 flat → fonction apprise mais eval mal exploitée"
echo "    * tout flat → pattern paradigm vraiment mort pour distillation"
echo "=========================================================="
