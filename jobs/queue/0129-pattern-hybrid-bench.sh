#!/usr/bin/env bash
# id: 0129-pattern-hybrid-bench
# description: Option F — pattern hybride (Scan-style) :
#   eval_final = handcrafted + pattern_correction
# Train target = (NNUE_score - handcrafted_score), bench Gate 2.
#
# Pre-condition : 0122bis (master rescored NNUE) + 0128 (master handcrafted) OK.
#
# Hypothèse : nos 5 variants linéaires précédents ont tous échoué parce
# qu'ils remplaçaient l'éval complète au lieu de l'augmenter. Hybride =
# l'architecture éprouvée de Scan (cf docs/SCAN_ARCHITECTURE §3).
#
# expected_duration: ~1h-1h30 wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0129-pattern-hybrid-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATA_NNUE=/root/jass/jobs/results/0122bis-rewrite-master-scores-v15-nnue/artefacts.src/master-1600-rescored.jnnw
DATA_HC=/root/jass/jobs/results/0128-rewrite-master-handcrafted/artefacts.src/master-1600-handcrafted.jnnw
[ -f "$DATA_NNUE" ] || { echo "ABORT: rescored NNUE master missing"; exit 3; }
[ -f "$DATA_HC" ]   || { echo "ABORT: handcrafted master missing (0128 not done?)"; exit 3; }

TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"
NCPU=$(nproc)

echo "=== host : $(hostname) ==="

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
echo "=== Phase 1 : build prod (bridge hybride) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train pattern résidu (target=score-handcrafted) ==="
WEIGHTS_OUT="$ART/pattern_jass_v7_hybrid.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$DATA_NNUE" \
    --skeleton-data "$DATA_HC" \
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
echo "=== Phase 3 : bench Gate 2 (bridge hybride) ==="
START_BENCH=$(date +%s)
./build-prod/jass --benchmark-pattern-jass "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-d6-pairs3.log"
BENCH_SEC=$(( $(date +%s) - START_BENCH ))

RATE=$(grep -oE 'PATTERN_JASS score rate: [0-9.]+' "$ART/bench-d6-pairs3.log" | head -1 | awk '{print $4}')
VERDICT=$(grep -E "^GATE 2 " "$ART/bench-d6-pairs3.log" | head -1)

echo
echo "=========================================================="
echo "       0129 OPTION F — PATTERN HYBRIDE VERDICT"
echo "=========================================================="
echo "  Historique complet (rate vs handcrafted, d6 pairs=3) :"
echo "    0118bis (wdl, 8×10 standalone)            : 0.000"
echo "    0119    (score=0 bug, 8×10 standalone)    : 0.000"
echo "    0120    (score=0 bug, 12×10 standalone)   : 0.000"
echo "    0123bis (score rescored, 12×10 standalone): 0.056"
echo "    0127    (score, 8×12 Scan-like standalone): 0.000"
echo "    0129    (HYBRID handcrafted+pattern)      : $RATE"
echo
echo "  train wall : ${TRAIN_SEC}s"
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
    print(f"  → ✅ OPTION F PASS Gate 2. Architecture Scan-style validée.")
    print(f"     L'erreur de nos 5 variants standalone est confirmée :")
    print(f"     pattern doit AUGMENTER handcrafted, pas le remplacer.")
elif rate > 0.51:
    print(f"  → marginal positif ({rate:.3f}). Pattern apporte un signal,")
    print(f"     mais petit ; tester avec plus d'iters ou L2 différent.")
elif rate >= 0.49:
    print(f"  → ~même force que handcrafted ({rate:.3f}). Pattern weights")
    print(f"     ne dégradent pas, mais n'apportent presque rien.")
else:
    print(f"  → régression ({rate:.3f}). Pattern weights nuisent ;")
    print(f"     overfitting + bridge intégré sub-optimal.")
EOF
fi
echo "=========================================================="
