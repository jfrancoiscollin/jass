#!/usr/bin/env bash
# id: 0128-rewrite-master-handcrafted
# description: Rewrite master JNNW scores avec l'eval handcrafted, pour
# servir de skeleton dans le training pattern hybride (Option F).
#
# Produit master-1600-handcrafted.jnnw aligné record-par-record avec
# master-1600-rescored.jnnw (0122bis). Le training pattern utilisera
# target = rescored.score - handcrafted.score (résidu).
#
# expected_duration: ~5-10 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0128-rewrite-master-handcrafted"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER_IN=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_IN" ] || { echo "ABORT: master missing"; exit 3; }

TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"

echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$(nproc)" --target jass \
    > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : rewrite scores via handcrafted evaluate() ==="
MASTER_OUT="$ART/master-1600-handcrafted.jnnw"
START=$(date +%s)
./build-prod/jass --rewrite-scores-with-handcrafted \
    "$MASTER_IN" "$MASTER_OUT" \
    2>&1 | tee "$ART/rewrite.log" | tail -5
RC=${PIPESTATUS[0]}
[ "$RC" -eq 0 ] || { echo "ABORT: rewrite failed"; exit 4; }
WALL=$(( $(date +%s) - START ))

ls -la "$MASTER_OUT"

echo
echo "=== Phase 3 : sanity Python preview ==="
python3 - <<EOF
import sys
sys.path.insert(0, '/root/jass/pattern_jass/tools')
import master_loader
ds = master_loader.load("$MASTER_OUT", max_records=10000)
import numpy as np
print(f"records      : {ds.n_records}")
print(f"score range  : [{int(ds.score.min())}, {int(ds.score.max())}]")
print(f"score std    : {ds.score.std():.2f}")
nz = int((ds.score != 0).sum())
print(f"non-zero     : {nz}/{ds.n_records} ({nz*100/ds.n_records:.1f}%)")
EOF

echo
echo "=========================================================="
echo "       0128 REWRITE MASTER HANDCRAFTED VERDICT"
echo "=========================================================="
echo "  wall   : ${WALL}s"
echo "  output : $MASTER_OUT"
echo "  Next : 0129 train pattern hybride (résidu vs handcrafted)"
echo "=========================================================="
