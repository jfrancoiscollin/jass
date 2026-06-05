#!/usr/bin/env bash
# id: 0120-pattern-jass-variant-B-geom
# description: Variant B — Phase Pattern-2 v2 : géométrie pattern
# enrichie (12 patterns au lieu de 8 : +4 diagonales/center).
#
# Hypothèse : 8 patterns row+col ne capturent pas assez les corrélations
# géométriques (notamment diagonales, qui sont cruciales en draughts).
# Variant B ajoute 4 patterns (3 diagonales + 1 central) → 12 × 59049
# = 708 588 buckets.
#
# Run sequentiel après Variant A (0119). Comparé à Variant A pour
# isoler l'effet "label score" vs "+géométrie".
#
# expected_duration: ~1h wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0120-pattern-jass-variant-B-geom"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master missing : $MASTER"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
NCPU=$(nproc)

echo
echo "=== Phase 0 : install scipy if missing ==="
if ! python3 -c "import scipy, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages \
            --no-cache-dir --quiet scipy numpy && break
        sleep 5
    done
    rm -rf "$PIP_SCRATCH"
fi

echo
echo "=== Phase 1 : build prod (12 patterns) ==="
rm -rf build-prod
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train v3 (target=score, 12 patterns × 59049 = 708K buckets) ==="
WEIGHTS_OUT="$ART/pattern_jass_v3_geom.pjtw"
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
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train failed rc=$TRAIN_RC"; exit 4; }

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
echo "       0120 VARIANT B (geom +diag) VERDICT"
echo "=========================================================="
echo "  vs 0118bis (wdl, 8 patterns) : rate 0.000"
echo "  vs 0119    (score, 8 patterns) : (see 0119)"
echo "  vs 0120    (score, 12 patterns) : $RATE"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else (float('inf') if rate==1 else -float('inf'))
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → VARIANT B PASS Gate 2. Géométrie enrichie suffit.")
elif rate >= 0.35:
    print(f"  → VARIANT B partiel ({rate:.3f}) ; comparer à A pour isoler l'effet.")
else:
    print(f"  → VARIANT B FAIL ({rate:.3f}). Géométrie ≠ root cause.")
    print(f"     Variant C (kings) reste à tester.")
EOF
fi
echo "=========================================================="
