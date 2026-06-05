#!/usr/bin/env bash
# id: 0119-pattern-jass-variant-A-score
# description: Variant A — Phase Pattern-2 v2 : train avec target=score
# (centipawn depth-20) au lieu de target=wdl (ternary), pour densifier
# le signal.
#
# Hypothèse (cf 0118bis verdict) : la WDL master est trop éparse pour
# permettre au modèle linéaire de généraliser. Le score depth-20 est
# beaucoup plus dense (chaque position a une valeur continue) et
# devrait permettre au pattern de capter du signal positionnel.
#
# Si Variant A passe Gate 2 → la racine du problème était le label,
# pas l'infra ni la géométrie.
# Si Variant A échoue → on passe à Variant B (Scan geometry).
#
# expected_duration: ~1h wall (train + bench identiques à 0118bis)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0119-pattern-jass-variant-A-score"
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
python3 -c "import scipy, numpy; print('scipy', scipy.__version__, 'numpy', numpy.__version__)" \
    || { echo "ABORT: scipy install failed"; exit 3; }

echo
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train pattern_jass v2 (target=score, clip ±2000cp) ==="
WEIGHTS_OUT="$ART/pattern_jass_v2_score.pjtw"
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
echo "       0119 VARIANT A (target=score) VERDICT"
echo "=========================================================="
echo "  vs 0118bis (target=wdl) :"
echo "    0118bis rate : 0.000 (0/54)"
echo "    0119    rate : $RATE"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else (float('inf') if rate==1 else -float('inf'))
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → VARIANT A PASS Gate 2. Le label score densifie le signal.")
    print(f"    Continuer Phase Pattern-3 (bootstrap Scan distillation).")
elif rate >= 0.30:
    print(f"  → VARIANT A améliore vs 0118bis (0.000) mais < Gate 2.")
    print(f"    Score densifie partiellement ; tester Variant B (Scan geometry).")
else:
    print(f"  → VARIANT A FAIL ({rate:.3f}).")
    print(f"    Label ≠ root cause. Passer à Variant B (Scan geometry).")
EOF
fi
echo "=========================================================="
