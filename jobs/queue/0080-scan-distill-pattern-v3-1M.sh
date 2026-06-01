#!/usr/bin/env bash
# id: 0080-scan-distill-pattern-v3-1M
# description: Test décisif pattern distillation à plein volume.
#
# 0079 sweep a montré : pattern V3 Adam s=0.01 lambda=1.0 sur 100K =
# pearson 0.78 (capture Scan eval correctement) mais 0/54 vs Scan car
# data trop petite (4.25M buckets / 100K records = 0.024 records/bucket,
# coverage terrible). MLP 0078 @ 1M = vs Scan 0.111.
#
# 0080 = pattern V3 Adam sur LE MÊME 1M dataset que 0078 MLP. Comparaison
# directe à volume égal. Si pearson maintient à 0.80+ et win-rate
# rattrape MLP, pattern paradigm est vraiment concurrent.
#
# Aussi : test bonus avec V2 patterns (16×8 = full-coverage, 16 × 3^8 =
# ~105K buckets, beaucoup mieux couvert par 1M data — ratio 1M/105K = 9.5
# records/bucket vs V3 0.235 records/bucket).
#
# Decision gate :
#   * pattern_V3 vs Scan > 0.10 → pattern paradigm vrai concurrent MLP
#   * pattern_V2 vs Scan > 0.15 → V2 (shorter patterns, denser coverage)
#     est l'archi pattern qui marche
#   * tout < 0.05 vs Scan → vraiment limité par autre chose, MLP gagne
#
# expected_duration: ~1-1.5h wall
#   * dataset 1M déjà distillé (réutilise 0078)
#   * V3 train Adam (60 epochs) : ~15-25 min
#   * V2 train Adam (60 epochs) : ~10-15 min (105K buckets, moins lourd)
#   * Bench × 2 × 4 : ~30 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0080-scan-distill-pattern-v3-1M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER_SAMPLE=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)

RELAB_1M=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$RELAB_1M" ] || { echo "ABORT: 0078 distilled 1M not found at $RELAB_1M"; exit 3; }

RELAB="$ART/v10-distilled-1M.bin"
cp "$RELAB_1M" "$RELAB"
echo "Using 1M distilled dataset : $RELAB_1M ($(stat -c%s "$RELAB_1M") bytes)"

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

# Two pattern archis to test (V3 = 8×12 verticals, V2 = 16×8 blocks).
# Adam optimizer with V1 config (s=0.01 l=1.0, best from 0079).
PATTERNS_LIST="v3 v2"
RESULTS=""
for PSET in $PATTERNS_LIST; do
    JPAT="$ART/pattern-$PSET-scan-1M.jpat"
    echo
    echo "=========================================================="
    echo "=== train pattern $PSET Adam 60ep sur 1M distilled ==="
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern.py \
        --data           "$RELAB" \
        --out            "$JPAT" \
        --patterns       "$PSET" \
        --hybrid \
        --pattern-base   3 \
        --init-man       100 --init-king 300 \
        --optimizer      adam \
        --epochs         60 \
        --lr             1e-3 \
        --lambda         1.0 \
        --score-scale    0.01 \
        --weight-decay   1e-5 \
        --symmetry \
        --num-seeds      1 \
        --seed           42 \
        2>&1 | tee "$ART/train-$PSET.log"
    T_SEC=$(( $(date +%s) - START ))
    ls -lh "$JPAT"

    # Pearson vs v7 (control)
    PEARSON="-"
    if [ -f "$MASTER_SAMPLE" ] && [ -n "$V7" ]; then
        python3 tools/pattern_eval_correlation.py \
            --pattern "$JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
            2>&1 | tee "$ART/pearson-$PSET.log"
        PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-$PSET.log" | head -1 | awk '{print $3}')
    fi

    # Bench vs Scan + v6/v7/v8 d10 3 pairs.
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$JPAT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$PSET-vs-scan-d10.log"
    R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-scan-d10.log" | head -1 | awk '{print $3}')

    [ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V6" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v6-d10.log"
    R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V7" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v7-d10.log"
    R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v8-d10.log"
    R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    RESULTS+="  $PSET (train ${T_SEC}s) : pearson $PEARSON  vs Scan $R_SCAN  vs v6 $R_V6  vs v7 $R_V7  vs v8 $R_V8"$'\n'
done

echo
echo "=========================================================="
echo "       0080 PATTERN DISTILL 1M VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Reference :"
echo "    MLP 0078 256-128 (1M) : vs Scan 0.028  vs v8 0.528"
echo "    MLP 0078 512-256 (1M) : vs Scan 0.111  vs v8 0.417"
echo "    Pattern V3 (100K)     : vs Scan 0.000  vs v8 0.222  pearson 0.78"
echo
echo "  Decision :"
echo "    * pattern vs Scan > 0.10 → pattern paradigm en vrai concurrent MLP"
echo "    * V2 > V3 → 16×8 patterns coverage denser"
echo "    * tout < 0.05 vs Scan → pattern vraiment plafonné, MLP wins"
echo "=========================================================="
