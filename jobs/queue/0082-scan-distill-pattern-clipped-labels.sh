#!/usr/bin/env bash
# id: 0082-scan-distill-pattern-clipped-labels
# description: Last shot pattern distillation — 2 fixes pour outliers.
#
# Diagnostic 0081 a révélé : Scan labels = std 2682, range ±30000 cp
# (forced-mate scores). v7 NNUE = std 615. Pattern model MSE compresse
# implicitement → std 157. Search jass calibré pour std ~400-500 →
# miscalibre → cutoffs ratés → 0/54.
#
# 2 approches au choix complémentaires :
#   (1) CLIP labels ±2000 + MSE  (kill outliers à la source)
#   (2) HUBER loss (delta=200/500) sans clip  (loss robuste, L1 sur outliers)
#
# Huber loss ajoutée à train_pattern.py dans le même commit
# (--loss-type huber --huber-delta D). Préserve fit normal range
# (L2 within ±delta) et L1-clips les outliers.
#
# 6 variantes au total :
#   clip2000 + V3 + MSE   (ref)
#   clip1000 + V3 + MSE   (aggressive clip)
#   nopclip + V3 + HUBER d=200
#   noclip + V3 + HUBER d=500
#   nopclip + V2 + HUBER d=200
#   nopclip + V2 + HUBER d=500
#
# Decision gate :
#   * any vs Scan > 0.10 OR vs v8 > 0.30 → pattern paradigm vit
#   * tout flat → pattern paradigm vraiment plafonné, drop pour MLP
#
# Réutilise dataset 1M de 0078. ~45-60 min wall.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0082-scan-distill-pattern-clipped-labels"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER_SAMPLE=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)

RELAB_1M=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$RELAB_1M" ] || { echo "ABORT: 0078 distilled 1M not found"; exit 3; }

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

# Create clipped datasets for 2 thresholds.
for CLIP in 2000 1000; do
    CLIPPED="$ART/v10-distilled-1M-clip${CLIP}.bin"
    python3 - <<EOF
import struct, statistics
from pathlib import Path
clip = $CLIP
src = Path("$RELAB_1M").read_bytes()
n = struct.unpack_from('<I', src, 4)[0]
out = bytearray(b"JNNW" + struct.pack("<I", n))
clipped_scores = []
for i in range(n):
    off = 8 + i * 38
    rec = src[off:off+38]
    score = struct.unpack_from('<i', rec, 33)[0]
    new_score = max(-clip, min(clip, score))
    clipped_scores.append(new_score)
    new_rec = rec[:33] + struct.pack("<i", new_score) + rec[37:38]
    out.extend(new_rec)
Path("$CLIPPED").write_bytes(bytes(out))
print(f"clip ±$CLIP : mean={statistics.mean(clipped_scores):.1f}  "
      f"std={statistics.stdev(clipped_scores):.1f}", flush=True)
EOF
done

# Variant configs : tag : dataset : pattern : extra-args
CONFIGS=(
    "c2000-v3-mse:$ART/v10-distilled-1M-clip2000.bin:v3:--loss-type mse"
    "c1000-v3-mse:$ART/v10-distilled-1M-clip1000.bin:v3:--loss-type mse"
    "noclip-v3-huber200:$RELAB_1M:v3:--loss-type huber --huber-delta 200"
    "noclip-v3-huber500:$RELAB_1M:v3:--loss-type huber --huber-delta 500"
    "noclip-v2-huber200:$RELAB_1M:v2:--loss-type huber --huber-delta 200"
    "noclip-v2-huber500:$RELAB_1M:v2:--loss-type huber --huber-delta 500"
)

RESULTS=""
for entry in "${CONFIGS[@]}"; do
    TAG="${entry%%:*}"
    rest="${entry#*:}"
    DATA="${rest%%:*}"
    rest="${rest#*:}"
    PSET="${rest%%:*}"
    EXTRA="${rest#*:}"
    JPAT="$ART/pattern-${TAG}.jpat"

    echo
    echo "=========================================================="
    echo "=== $TAG : $PSET on $(basename $DATA) ==="
    echo "    args: $EXTRA"
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern.py \
        --data           "$DATA" \
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
        $EXTRA \
        2>&1 | tee "$ART/train-$TAG.log"
    T_SEC=$(( $(date +%s) - START ))

    PEARSON="-"; PSTD="-"; RSTD="-"
    if [ -f "$MASTER_SAMPLE" ] && [ -n "$V7" ]; then
        python3 tools/pattern_eval_correlation.py \
            --pattern "$JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
            2>&1 | tee "$ART/pearson-$TAG.log"
        PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-$TAG.log" | head -1 | awk '{print $3}')
        PSTD=$(grep -oE 'pattern : .*std=[0-9.]+' "$ART/pearson-$TAG.log" | head -1 | grep -oE 'std=[0-9.]+' | cut -d= -f2)
        RSTD=$(grep -oE 'ref *: .*std=[0-9.]+' "$ART/pearson-$TAG.log" | head -1 | grep -oE 'std=[0-9.]+' | cut -d= -f2)
    fi

    ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$TAG-vs-v8.log"
    R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$TAG-vs-v8.log" 2>/dev/null | head -1 | awk '{print $3}')

    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$JPAT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$TAG-vs-scan.log"
    R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$TAG-vs-scan.log" | head -1 | awk '{print $3}')

    RESULTS+="  $TAG (train ${T_SEC}s) : pearson $PEARSON std=$PSTD (ref=$RSTD)  vs Scan $R_SCAN  vs v8 $R_V8"$'\n'
done

echo
echo "=========================================================="
echo "       0082 PATTERN OUTLIER-FIX SWEEP VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Reference :"
echo "    Pattern V3 1M unfixed (0080)  : std=157 pearson 0.79 vs Scan 0.000 vs v8 0.222"
echo "    Pattern V3 1M scaled (0081)   : std=115 pearson 0.80 vs Scan 0.000 vs v8 0.000"
echo
echo "  Decision :"
echo "    * any vs Scan > 0.10 OR vs v8 > 0.30 → pattern paradigm vit"
echo "    * Huber > clip → loss robust wins, recommandation pour futurs jobs"
echo "    * tout flat → pattern paradigm vraiment plafonné, drop pour MLP"
echo "=========================================================="
