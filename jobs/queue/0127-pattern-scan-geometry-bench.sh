#!/usr/bin/env bash
# id: 0127-pattern-scan-geometry-bench
# description: Option D — Scan-style geometry (8 patterns × 12 squares,
# 4.25M buckets) + target=score sur master rescored.
#
# Pre-condition : master-1600-rescored.jnnw existe (0122bis OK).
#
# Si Gate 2 PASS (rate ≥ 0.55) : géométrie Scan-style suffit, infra
# pattern jass validée. Sinon : pattern lookup linéaire est plafonné
# quelle que soit la géométrie, pivot vers MLP (option E).
#
# expected_duration: ~1h-1h30 wall (train + bench, weights file ~17MB)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0127-pattern-scan-geometry-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0122bis-rewrite-master-scores-v15-nnue/artefacts.src/master-1600-rescored.jnnw
[ -f "$MASTER" ] || { echo "ABORT: rescored master missing"; exit 3; }

TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"
NCPU=$(nproc)

echo "=== host : $(hostname)  nproc: $NCPU ==="

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
echo "=== Phase 1 : build prod (Scan-style 8×12 patterns) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train target=score sur master RESCORED, 4.25M buckets ==="
WEIGHTS_OUT="$ART/pattern_jass_v6_scan.pjtw"
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
ls -la "$WEIGHTS_OUT"

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
echo "       0127 OPTION D — SCAN GEOMETRY VERDICT"
echo "=========================================================="
echo "  Historique :"
echo "    0118bis (wdl, 8×10 patterns)              : 0.000"
echo "    0119    (score=0 par bug, 8×10)           : 0.000"
echo "    0120    (score=0 par bug, 12×10)          : 0.000"
echo "    0123bis (score rescored, 12×10)           : 0.056"
echo "    0127    (score rescored, 8×12 Scan-like)  : $RATE"
echo
echo "  train wall : ${TRAIN_SEC}s ($(( TRAIN_SEC / 60 ))m)"
echo "  bench wall : ${BENCH_SEC}s"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else (float('inf') if rate==1 else -float('inf'))
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → OPTION D PASS Gate 2. Géométrie Scan-style résout.")
elif rate >= 0.30:
    print(f"  → Amélioration partielle ({rate:.3f} vs 0.056). Géométrie aide,")
    print(f"    mais pas suffisamment. Option E (MLP) à considérer.")
else:
    print(f"  → FAIL ({rate:.3f}). Pattern lookup linéaire plafonné.")
    print(f"     Conclusion : sans MLP, pattern paradigm ne battra pas handcrafted.")
EOF
fi
echo "=========================================================="
