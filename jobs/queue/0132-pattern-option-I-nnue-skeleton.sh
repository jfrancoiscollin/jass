#!/usr/bin/env bash
# id: 0132-pattern-option-I-nnue-skeleton
# description: Option I — pattern hybride avec v15 NNUE 128-64 comme
# squelette (au lieu de handcrafted). Validé après 0131 régression :
# corr(Scan, handcrafted) = 0.44 trop bas, résidu pas fittable.
#
# Hypothèse : corr(Scan, v15) ~0.95 → résidu petit → fittable.
#
# Pipeline :
#  1. Reuse master-1500K Scan d10 labels (0131)
#  2. Reuse master-sample-1500K positions (0131)
#  3. Compute v15 NNUE scores sur les 1.5M positions (skeleton)
#  4. Train pattern : target = scan_score - v15_score
#  5. Bench --benchmark-pattern-jass-nnue-skel
#
# expected_duration: ~15-25 min wall (la plus grosse partie est l'eval
# v15 sur 1.5M positions, ~5-10 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0132-pattern-option-I-nnue-skeleton"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Réutilise les artefacts de 0131
DATA_SCAN=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/master-1500K-scan-d10.jnnw
SAMPLE=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/master-sample-1500K.jnnw
[ -f "$DATA_SCAN" ] || { echo "ABORT: 0131 scan-labelled missing"; exit 3; }
[ -f "$SAMPLE" ]    || { echo "ABORT: 0131 sample missing"; exit 3; }

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights missing"; exit 3; }

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
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : compute v15 NNUE scores sur 1.5M positions (skeleton) ==="
V15_SCORES="$ART/master-1500K-v15.jnnw"
START=$(date +%s)
./build-prod/jass --rewrite-scores-with-nnue "$SAMPLE" "$V15_SCORES" --nnue "$V15" \
    > "$ART/v15-rewrite.log" 2>&1
RC=${PIPESTATUS[0]}
[ "$RC" -eq 0 ] || { echo "ABORT: v15 rewrite"; tail "$ART/v15-rewrite.log"; exit 4; }
V15_WALL=$(( $(date +%s) - START ))
echo "  v15 rewrite wall : ${V15_WALL}s"

echo
echo "=== Phase 3 : preview corr(scan, v15) ==="
python3 - <<EOF
import sys
sys.path.insert(0, '/root/jass/pattern_jass/tools')
import master_loader
import numpy as np
scan = master_loader.load("$DATA_SCAN", max_records=50000)
v15  = master_loader.load("$V15_SCORES", max_records=50000)
hc_path = "/root/jass/jobs/results/0128-rewrite-master-handcrafted/artefacts.src/master-1600-handcrafted.jnnw"
print(f"scan std = {scan.score.std():.1f}cp,  v15 std = {v15.score.std():.1f}cp")
corr_scan_v15 = np.corrcoef(scan.score.astype(float), v15.score.astype(float))[0,1]
print(f"corr(scan, v15) = {corr_scan_v15:.4f}")
diff = scan.score.astype(float) - v15.score.astype(float)
print(f"residual (scan - v15) : std = {diff.std():.1f}cp, mean = {diff.mean():+.1f}")
EOF

echo
echo "=== Phase 4 : train pattern résidu (target = scan - v15) ==="
WEIGHTS_OUT="$ART/pattern_jass_v10_option_I.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$DATA_SCAN" \
    --skeleton-data "$V15_SCORES" \
    --out  "$WEIGHTS_OUT" \
    --target score --score-clip 5000 \
    --l2 1e-5 --max-iter 200 --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

echo
echo "=== Phase 5a : bench pattern+v15-skeleton vs handcrafted ==="
./build-prod/jass --benchmark-pattern-jass-nnue-skel "$WEIGHTS_OUT" "$V15" 6 3 \
    2>&1 | tee "$ART/bench-vs-hc-d6.log"
RATE_HC=$(grep -oE 'rate vs handcrafted: [0-9.]+' "$ART/bench-vs-hc-d6.log" | head -1 | awk '{print $4}')

echo
echo "=== Phase 5b : bench pattern+v15 vs v15-only (test si pattern AJOUTE) ==="
./build-prod/jass --benchmark-nnue-vs-nnue \
    "$WEIGHTS_OUT" "$V15" 6 3 2>&1 | tee "$ART/bench-vs-v15-d6.log" 2>/dev/null \
    || echo "  (mode incompatible PJTW pour --benchmark-nnue-vs-nnue)"
RATE_VS_V15=$(grep -oE 'A score rate: [0-9.]+' "$ART/bench-vs-v15-d6.log" 2>/dev/null | head -1 | awk '{print $4}')

echo
echo "=========================================================="
echo "       0132 OPTION I — PATTERN + NNUE SKELETON VERDICT"
echo "=========================================================="
echo "  Historique pattern hybride :"
echo "    0129 (v15-label + handcrafted-skel)        : 0.667"
echo "    0130 (Scan d12 + handcrafted-skel, 200K)   : 0.083"
echo "    0131 (Scan d10 + handcrafted-skel, 1.5M)   : 0.000"
echo "    0132 (Scan d10 + v15-skel, 1.5M, OPTION I) : $RATE_HC vs hc"
echo "                                                ${RATE_VS_V15:-n/a} vs v15"
echo
echo "  v15 rewrite  : ${V15_WALL}s"
echo "  train wall   : ${TRAIN_SEC}s"
echo
if [ -n "$RATE_HC" ]; then
    python3 - <<EOF
import math
r = float("$RATE_HC")
elo = -400 * math.log10(1/r - 1) if 0 < r < 1 else (float('inf') if r==1 else -float('inf'))
print(f"  vs handcrafted rate {r:.3f} = ΔELO ≈ {elo:+.0f}")
if r >= 0.80:
    print(f"  → Option I PASS spectaculaire — pattern + NNUE bat handcrafted très fort")
elif r >= 0.65:
    print(f"  → Option I PASS — confirme intuition NNUE-skeleton")
else:
    print(f"  → résultat modeste ({r:.3f}). Vérifier corr(scan, v15) et résidu.")
EOF
fi
echo "=========================================================="
