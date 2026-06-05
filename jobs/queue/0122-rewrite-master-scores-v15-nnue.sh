#!/usr/bin/env bash
# id: 0122-rewrite-master-scores-v15-nnue
# description: Pivot critique — reécrire les scores du master 1.6M
# avec l'eval NNUE v15 128-64. Le master a été créé avec score=0 par
# design (cf tools/pdn_to_jnnw.py:43), ce qui rend tous les --target
# score inutilisables. Cette job génère master-rescored.jnnw avec
# scores NNUE 1-ply, ouvrant la voie aux variants pattern à target=score.
#
# Pourquoi 1-ply (eval direct) et pas search depth-N ?
#  - 1-ply : ~5-15 min pour 4.7M positions. Suffisant pour signal pattern.
#  - depth-N : heures+. Overkill pour POC pattern lookup.
#
# expected_duration: ~15-30 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0122-rewrite-master-scores-v15-nnue"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER_IN=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_IN" ] || { echo "ABORT: master missing"; exit 3; }

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights missing"; exit 3; }

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
echo "input : $MASTER_IN ($(du -h $MASTER_IN | cut -f1))"
echo "nnue  : $V15"

echo
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$(nproc)" --target jass \
    > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

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
echo "=== Phase 3 : sanity check (Python preview) ==="
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
print()
print("WDL distribution :")
for v in [-1, 0, 1]:
    n = int((ds.wdl == v).sum())
    print(f"  wdl={v:+d} : {n} ({n*100/ds.n_records:.1f}%)")
EOF

echo
echo "=========================================================="
echo "       0122 REWRITE MASTER SCORES VERDICT"
echo "=========================================================="
echo "  wall      : ${WALL}s"
echo "  output    : $MASTER_OUT"
echo
echo "Next : 0123 re-train Variant B (12 patterns, target=score) sur"
echo "       master-rescored, vrai bench Gate 2."
echo "=========================================================="
