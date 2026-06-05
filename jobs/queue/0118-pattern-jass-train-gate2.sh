#!/usr/bin/env bash
# id: 0118-pattern-jass-train-gate2
# description: Production training pattern_jass v1 sur master 1.6M +
# bench Gate 2 (vs handcrafted via --benchmark-pattern-jass).
#
# Phase Pattern-2 Day 5 — verdict réel.
#
# Pipeline :
#  1. Build prod (avec pattern_jass_bridge linké, post-#181)
#  2. Train Python L-BFGS sur master 1.6M, 200 iters, λ=1e-5
#  3. Bench --benchmark-pattern-jass d6 pairs=3 (54 games)
#  4. Verdict Gate 2 :
#       rate ≥ 0.55 → infra pattern jass fonctionne, continuer Phase
#                     Pattern-3 (bootstrap Scan distillation)
#       rate <  0.55 → infra ne marche PAS sur draughts (la POC Othello
#                     l'élimine ; faut investiguer pourquoi draughts
#                     spécifiquement)
#
# expected_duration: ~1h wall (train ~20min, bench ~30min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0118-pattern-jass-train-gate2"
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
echo "=== Phase 1 : build prod (avec pattern_jass_bridge) ==="
rm -rf build-prod
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train pattern_jass v1 sur master 1.6M ==="
WEIGHTS_OUT="$ART/pattern_jass_v1.pjtw"
python3 -m pip install --quiet scipy numpy 2>/dev/null || true
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$MASTER" \
    --out  "$WEIGHTS_OUT" \
    --l2 1e-5 \
    --max-iter 200 \
    --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train failed rc=$TRAIN_RC"; exit 4; }
echo "  train wall: ${TRAIN_SEC}s ($(( TRAIN_SEC / 60 ))m $(( TRAIN_SEC % 60 ))s)"

ls -la "$WEIGHTS_OUT" || { echo "ABORT: no weights output"; exit 4; }

echo
echo "=== Phase 3 : bench --benchmark-pattern-jass depth 6 pairs 3 ==="
START_BENCH=$(date +%s)
./build-prod/jass --benchmark-pattern-jass "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-d6-pairs3.log"
BENCH_SEC=$(( $(date +%s) - START_BENCH ))
echo "  bench wall: ${BENCH_SEC}s"

RATE=$(grep -oE 'PATTERN_JASS score rate: [0-9.]+' "$ART/bench-d6-pairs3.log" | head -1 | awk '{print $4}')
VERDICT=$(grep -E "^GATE 2 " "$ART/bench-d6-pairs3.log" | head -1)

echo
echo "=========================================================="
echo "       0118 PATTERN_JASS GATE 2 VERDICT"
echo "=========================================================="
echo "  train      : ${TRAIN_SEC}s ($(( TRAIN_SEC / 60 ))m)"
echo "  bench      : ${BENCH_SEC}s"
echo "  weights    : $WEIGHTS_OUT ($(ls -la "$WEIGHTS_OUT" | awk '{print $5}') bytes)"
echo "  rate       : $RATE"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else float('inf')
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → GATE 2 PASS : pattern_jass v1 ≥ handcrafted ({rate:.3f})")
    print(f"  → continuer Phase Pattern-3 (bootstrap Scan distillation)")
elif rate >= 0.45:
    print(f"  → GATE 2 marginal ({rate:.3f}) : pattern peu différent de hc")
    print(f"  → tester variants (MG/EG split, plus de patterns, plus de data)")
else:
    print(f"  → GATE 2 FAIL ({rate:.3f}) : pattern_jass insuffisant")
    print(f"  → l'infra Othello marchait, donc le pb est draughts-spécifique")
    print(f"     hypothèses : géométrie pattern, encoding, kings ignorés, ...")
EOF
fi
echo "=========================================================="
