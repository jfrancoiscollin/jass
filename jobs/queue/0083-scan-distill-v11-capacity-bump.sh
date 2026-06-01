#!/usr/bin/env bash
# id: 0083-scan-distill-v11-capacity-bump
# description: Phase G.3(a) — cascading distillation capacity step.
#
# 0078 a montré sur 1M Scan-distilled :
#   * 256-128 : vs Scan 0.028  vs v8 0.528
#   * 512-256 : vs Scan 0.111  vs v8 0.417
# 1024-512 jamais testé. Avec 1M records / 1.45M params = ratio 0.69
# (sous-saturé mais limite). Test si capacité plus haute exploite mieux
# le signal Scan.
#
# Aussi : 768-384 comme variante intermédiaire (650K params, ratio 1.5,
# bien saturé).
#
# Decision gate :
#   * 1024-512 vs Scan > 0.15 → bump capacity = next leap (0084 = scale 5M)
#   * 768-384 ≈ 1024-512 → 1024 trop gros, ship 768-384 comme v11
#   * tout < 512-256 (0.111 vs Scan) → capacity saturée, scale data ou
#                                       cascading par self-play (option b/c)
#
# Coût : ~30-45 min (skip relabel, juste train + bench)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0083-scan-distill-v11-capacity-bump"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V10_256=$(ls -t /root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/arch-256-128/nnue-*-q.bin 2>/dev/null | head -1)
V10_512=$(ls -t /root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/arch-512-256/nnue-*-q.bin 2>/dev/null | head -1)

RELAB_1M=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$RELAB_1M" ] || { echo "ABORT: 0078 distilled 1M not found"; exit 3; }

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

# Sweep 2 archis sur 0078 1M Scan-distilled (no master, pure distillation).
RESULTS=""
for ARCH in 1024-512 768-384; do
    ARCH_DIR="$ART/arch-$ARCH"
    mkdir -p "$ARCH_DIR"
    echo
    echo "=========================================================="
    echo "=== train v11 $ARCH PURE distillation sur 1M ==="
    echo "=========================================================="
    START_T=$(date +%s)
    python3 tools/train_v3.py \
        --data                "$RELAB_1M" \
        --wdl-scale           400 \
        --bce-scale           50000 \
        --archs               "$ARCH" \
        --encoding            halfmen \
        --epochs              30 \
        --batch               512 \
        --out-dir             "$ARCH_DIR" \
        2>&1 | tee "$ART/train-$ARCH.log"
    T_SEC=$(( $(date +%s) - START_T ))

    BIN="$ARCH_DIR/nnue-$ARCH.bin"
    QUANT="$ARCH_DIR/nnue-$ARCH-q.bin"
    python3 tools/quantize_mlp.py --in "$BIN" --data "$RELAB_1M" --out "$QUANT" \
        2>&1 | tee "$ART/quantize-$ARCH.log"

    echo "=== bench $ARCH vs Scan / v6 / v7 / v8 / v10-256 / v10-512 d10 ==="
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$QUANT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$ARCH-vs-scan-d10.log"
    R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-scan-d10.log" | head -1 | awk '{print $3}')

    [ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V6" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v6-d10.log"
    R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V7" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v7-d10.log"
    R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v8-d10.log"
    R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V10_256" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V10_256" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v10-256-d10.log"
    R_V10_256=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v10-256-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V10_512" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V10_512" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v10-512-d10.log"
    R_V10_512=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v10-512-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    RESULTS+="  $ARCH (train ${T_SEC}s) : vs Scan $R_SCAN  vs v6 $R_V6  vs v7 $R_V7  vs v8 $R_V8  vs v10-256 $R_V10_256  vs v10-512 $R_V10_512"$'\n'
done

echo
echo "=========================================================="
echo "       0083 V11 CAPACITY BUMP VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Reference (0078) :"
echo "    v10 256-128 (1M) : vs Scan 0.028  vs v8 0.528"
echo "    v10 512-256 (1M) : vs Scan 0.111  vs v8 0.417"
echo
echo "  Decision :"
echo "    * 1024-512 vs Scan > 0.15 → capacity bump = next leap, scale 5M (0084)"
echo "    * 768-384 ≈ 1024-512 → ship 768-384 comme v11 (smaller, faster)"
echo "    * tout < 0.111 (= 512-256) → capacity saturée, pivot self-play (b/c)"
echo "=========================================================="
