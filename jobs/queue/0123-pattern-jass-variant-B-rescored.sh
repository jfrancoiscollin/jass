#!/usr/bin/env bash
# id: 0123-pattern-jass-variant-B-rescored
# description: Re-test Variant B (12 patterns, target=score) sur le
# master rescored par 0122 (v15 NNUE 1-ply scores).
#
# Pre-condition : 0122 doit avoir produit master-1600-rescored.jnnw.
#
# expected_duration: ~1h wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0123-pattern-jass-variant-B-rescored"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0122-rewrite-master-scores-v15-nnue/artefacts.src/master-1600-rescored.jnnw
[ -f "$MASTER" ] || { echo "ABORT: rescored master missing (0122 not done?)"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
NCPU=$(nproc)

echo
echo "=== Phase 0 : install scipy ==="
if ! python3 -c "import scipy, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"; mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages \
            --no-cache-dir --quiet scipy numpy && break
        sleep 5
    done
    rm -rf "$PIP_SCRATCH"
fi

echo
echo "=== Phase 1 : build prod (12 patterns from main) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train target=score sur master RESCORED ==="
WEIGHTS_OUT="$ART/pattern_jass_v5_rescored.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$MASTER" \
    --out  "$WEIGHTS_OUT" \
    --target score \
    --score-clip 2000 \
    --l2 1e-5 \
    --max-iter 200 \
    --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

echo
echo "=== Phase 3 : bench Gate 2 ==="
START_BENCH=$(date +%s)
./build-prod/jass --benchmark-pattern-jass "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-d6-pairs3.log"
BENCH_SEC=$(( $(date +%s) - START_BENCH ))

RATE=$(grep -oE 'PATTERN_JASS score rate: [0-9.]+' "$ART/bench-d6-pairs3.log" | head -1 | awk '{print $4}')
VERDICT=$(grep -E "^GATE 2 " "$ART/bench-d6-pairs3.log" | head -1)

echo
echo "=========================================================="
echo "       0123 VARIANT B RESCORED VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s"
echo "  bench wall : ${BENCH_SEC}s"
echo "  rate       : $RATE"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else (float('inf') if rate==1 else -float('inf'))
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → GATE 2 PASS. Infra pattern jass validée avec scores rescored.")
elif rate >= 0.40:
    print(f"  → Partiel ({rate:.3f}). Signal présent, peut-être que kings (Variant C) finit la marge.")
else:
    print(f"  → FAIL ({rate:.3f}). Pattern lookup ne suffit pas sur draughts master.")
    print(f"     Pivot : Phase Pattern-3 (Scan distillation directe) ou abandonner pattern paradigm.")
EOF
fi
echo "=========================================================="
