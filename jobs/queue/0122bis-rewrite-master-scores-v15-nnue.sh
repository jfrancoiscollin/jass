#!/usr/bin/env bash
# id: 0122bis-rewrite-master-scores-v15-nnue
# description: Re-run 0122 avec fix TMPDIR explicite + diag disque.
# 0122 a failed avec "can't open /tmp/cc*.s" → /tmp saturé ou IO issue.
#
# expected_duration: ~20-30 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0122bis-rewrite-master-scores-v15-nnue"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER_IN=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_IN" ] || { echo "ABORT: master missing"; exit 3; }

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights missing"; exit 3; }

echo "=== Phase 0 : disk space diag ==="
df -h / /tmp /root | tee "$ART/df-before.log"
echo
echo "/tmp content size :"
du -sh /tmp 2>/dev/null | head
ls /tmp/ 2>/dev/null | head -10

echo
echo "=== Phase 0b : ensure TMPDIR is on a healthy mount ==="
TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"
export TMP="$TMPDIR_REAL"
export TEMP="$TMPDIR_REAL"
df -h "$TMPDIR_REAL" | tee -a "$ART/df-before.log"

echo
echo "=== Phase 1 : build prod (TMPDIR=$TMPDIR) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$(nproc)" --target jass \
    > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL — retrying with j1"
    cmake --build build-prod -j1 --target jass \
        >> "$ART/build.log" 2>&1 || {
        echo "BUILD FAIL even at j1"
        tail -40 "$ART/build.log"
        df -h /tmp "$TMPDIR_REAL"
        exit 5
    }
}

echo
echo "=== Phase 2 : rewrite master scores via v15 NNUE eval ==="
MASTER_OUT="$ART/master-1600-rescored.jnnw"
START=$(date +%s)
./build-prod/jass --rewrite-scores-with-nnue \
    "$MASTER_IN" "$MASTER_OUT" --nnue "$V15" \
    2>&1 | tee "$ART/rewrite.log" | tail -10
RC=${PIPESTATUS[0]}
[ "$RC" -eq 0 ] || { echo "ABORT: rewrite failed rc=$RC"; exit 4; }
WALL=$(( $(date +%s) - START ))
echo "  wall: ${WALL}s ($(( WALL / 60 ))m)"

ls -la "$MASTER_OUT"

echo
echo "=== Phase 3 : sanity Python preview ==="
python3 - <<EOF
import sys
sys.path.insert(0, '/root/jass/pattern_jass/tools')
import master_loader
ds = master_loader.load("$MASTER_OUT", max_records=10000)
import numpy as np
print(f"records loaded     : {ds.n_records}")
print(f"score range        : [{int(ds.score.min())}, {int(ds.score.max())}]")
print(f"score std          : {ds.score.std():.2f}")
print(f"score mean         : {ds.score.mean():.2f}")
nz = int((ds.score != 0).sum())
print(f"non-zero scores    : {nz}/{ds.n_records} ({nz*100/ds.n_records:.1f}%)")
EOF

echo
echo "=========================================================="
echo "       0122bis REWRITE MASTER SCORES VERDICT"
echo "=========================================================="
echo "  wall      : ${WALL}s"
echo "  output    : $MASTER_OUT"
echo "Next : 0123bis re-train Variant B sur master-rescored."
echo "=========================================================="
