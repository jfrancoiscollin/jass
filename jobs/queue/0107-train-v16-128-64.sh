#!/usr/bin/env bash
# id: 0107-train-v16-128-64
# description: Train v16 128-64 sur master (1.6M) + 0106 gen-2M depth 20.
# Pipeline Phase 2 suite : 0106 → 0107 → 0108.
#
# Stratégie : 128-64 est notre sweet spot (0090 sweep). On garde l'arch
# et on injecte la nouvelle data self-play depth 20. Loss BCE sur les
# master games (WDL ternaire), MSE sur les 2M (regression de score).
#
# Combined dataset : 1.6M master + 2M gen = 3.6M training records.
# Epochs : 30 (même que 0056). Batch 512.
#
# Sortie : v16 128-64 quantisé + bench vs v15 et vs Scan d10.
#
# expected_duration: ~4-8h sur 8 vCPU (CPU training, 30 epochs × 3.6M)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0107-train-v16-128-64"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Inputs
GEN_2M=/root/jass/jobs/results/0106-gen-data-depth20-2M/artefacts.src/gen-2M-depth20.bin
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
SCAN_BIN=/root/jass-scan/scan_linux

[ -f "$GEN_2M" ]   || { echo "ABORT: 0106 gen output missing : $GEN_2M"; exit 3; }
[ -f "$MASTER" ]   || { echo "ABORT: master missing"; exit 3; }
[ -n "$V15_128_64" ] && [ -f "$V15_128_64" ] || { echo "ABORT: v15 missing"; exit 3; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan missing"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== inputs ==="
ls -la "$GEN_2M" "$MASTER" "$V15_128_64"

echo
echo "=== build prod ==="
if [ ! -x ./build/jass ]; then
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
fi
cmake --build build -j"$(nproc)" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

# Phase 1 : train 128-64 with combined master + 2M
echo
echo "=== Phase 1 : train v16 128-64 (master+2M, 30 epochs) ==="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$GEN_2M" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  2000000 \
    --archs               128-64 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

BEST_BIN="$ART/nnue-128-64.bin"
QUANT_OUT="$ART/nnue-128-64-q.bin"
[ -f "$BEST_BIN" ] || { echo "ABORT: no output bin"; exit 4; }

echo
echo "=== Phase 2 : quantize ==="
python3 tools/quantize_mlp.py --in "$BEST_BIN" --data "$GEN_2M" --out "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"
[ -f "$QUANT_OUT" ] || { echo "ABORT: quantize failed"; exit 4; }

# Phase 3 : bench v16 vs v15 (head-to-head) + vs Scan
echo
echo "=== Phase 3a : bench v16 vs v15 d10 (3 pairs) ==="
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V15_128_64" 10 3 \
    2>&1 | tee "$ART/bench-v16-vs-v15-d10.log"

echo
echo "=== Phase 3b : bench v16 vs Scan d10 (3 pairs) ==="
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$QUANT_OUT" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-v16-vs-scan-d10.log" | tail -10

# Verdict
RATE_V15=$(grep -oE 'A score rate: [0-9.]+' "$ART/bench-v16-vs-v15-d10.log" | head -1 | awk '{print $4}')
RATE_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-v16-vs-scan-d10.log" | head -1 | awk '{print $3}')
RATE_SCAN_V15=0.870  # baseline mesurée v15 vs Scan d10

echo
echo "=========================================================="
echo "       0107 v16 128-64 TRAINING VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s ($(( TRAIN_SEC / 3600 ))h $(( (TRAIN_SEC % 3600) / 60 ))min)"
echo "  output     : $QUANT_OUT"
echo
echo "  v16 vs v15 d10 (3 pairs = ~24 games)"
echo "    A score rate: $RATE_V15"
echo
echo "  v16 vs Scan d10 (3 pairs = ~54 games)"
echo "    score rate: $RATE_SCAN  (v15 baseline: $RATE_SCAN_V15)"
echo
python3 - <<EOF
v15_rate = float("$RATE_V15") if "$RATE_V15" else None
scan_rate = float("$RATE_SCAN") if "$RATE_SCAN" else None
if v15_rate is not None:
    import math
    elo = -400 * math.log10(1/v15_rate - 1) if 0 < v15_rate < 1 else float('inf')
    if v15_rate > 0.55:
        print(f"  → v16 GAGNE vs v15 ({v15_rate:.3f}, ΔELO≈{elo:+.0f}). Phase 2 réussie.")
    elif v15_rate > 0.50:
        print(f"  → v16 marginal vs v15 ({v15_rate:.3f}, ΔELO≈{elo:+.0f}). Signal faible.")
    else:
        print(f"  → v16 N'AMÉLIORE PAS v15 ({v15_rate:.3f}). Le 2M depth 20 n'a pas apporté.")
if scan_rate is not None:
    print(f"  → vs Scan d10 : v16 {scan_rate:.3f} vs v15 baseline 0.870 (delta {scan_rate - 0.870:+.3f})")
EOF
echo "=========================================================="
