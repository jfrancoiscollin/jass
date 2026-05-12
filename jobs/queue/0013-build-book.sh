#!/usr/bin/env bash
# id: 0013-build-book
# description: Build a depth-12 opening book over the 77 560 user-
#              provided positions at the root of the repo
#              (positions (2).fen). The C++ --build-book mode is
#              single-threaded; we shard the FEN list across nproc
#              parallel jass workers and merge the resulting partial
#              .bok files with tools/merge_jbok.py.
#
#              Expected speedup: ~4x on 4 vCPU (gen-data scaled
#              similarly in 0007). At ~50-100 positions/sec/CPU at
#              depth 12, 77K / 4 / 75 ≈ 4-5 min wall. Round up for
#              startup / cleanup.
# expected_duration: ~15-30 min on 4 vCPU CCX23
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0013-build-book"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

FENS="/root/jass/positions (2).fen"
if [ ! -f "$FENS" ]; then
    echo "ABORT: $FENS not found at repo root"
    ls -la /root/jass/*.fen 2>/dev/null || echo "  (no .fen files at repo root)"
    exit 3
fi

DEPTH=12
NSHARDS=$(nproc)
LINES=$(wc -l < "$FENS")
echo "=== host facts ==="
echo "host:     $(hostname)"
echo "nproc:    $(nproc)"
echo "fens:     $FENS ($LINES lines)"
echo "depth:    $DEPTH"
echo "shards:   $NSHARDS"

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:     $(./build/jass --version)"

echo
echo "=== sharding FEN list across $NSHARDS chunks ==="
# `split -n l/N` divides by LINES, keeping each line intact in exactly
# one shard. Suffix -d gives numeric suffixes (00, 01, …).
split -n "l/$NSHARDS" -d --suffix-length=2 "$FENS" "$ART/shard-"
ls -la "$ART"/shard-* | head -10

echo
echo "=== launching $NSHARDS parallel --build-book workers ==="
START=$(date +%s)
pids=()
for f in "$ART"/shard-*; do
    shard_id=$(basename "$f" | sed 's/shard-//')
    (
        START_SH=$(date +%s)
        ./build/jass --build-book "$f" "$ART/partial-${shard_id}.bok" "$DEPTH" \
            > "$ART/shard-${shard_id}.log" 2>&1
        rc=$?
        END_SH=$(date +%s)
        echo "$rc $((END_SH - START_SH))" > "$ART/shard-${shard_id}.result"
        exit $rc
    ) &
    pids+=($!)
    echo "  shard $shard_id launched as pid $!"
done

echo
echo "=== waiting on all shards ==="
fail=0
for i in "${!pids[@]}"; do
    p="${pids[$i]}"
    if wait "$p"; then
        echo "  pid $p: OK"
    else
        rc=$?
        echo "  pid $p: FAILED rc=$rc"
        fail=$((fail + 1))
    fi
done
END=$(date +%s)
WALL=$((END - START))

echo
echo "=== per-shard rc / seconds ==="
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] || continue
    echo "  $(basename $f): $(cat $f)"
done

if [ "$fail" -gt 0 ]; then
    echo
    echo "=== $fail shard(s) failed — heads of failing logs ==="
    for f in "$ART"/shard-*.result; do
        rc=$(awk '{print $1}' "$f" 2>/dev/null)
        if [ "$rc" != "0" ]; then
            shard_id=$(basename "$f" | sed 's/shard-//;s/\.result//')
            echo "--- shard $shard_id (rc=$rc) ---"
            head -30 "$ART/shard-${shard_id}.log" || true
        fi
    done
    exit 4
fi

echo
echo "=== merging partial .bok files ==="
python3 tools/merge_jbok.py \
    --out "$ART/openings-77k-depth${DEPTH}.bok" \
    "$ART"/partial-*.bok

# Sanity-load the merged book through Jass.
echo
echo "=== sanity-load merged book in Jass ==="
echo "position fen W:W31-50:B1-20" \
    | ./build/jass --book "$ART/openings-77k-depth${DEPTH}.bok" 2>&1 | head -5

echo
echo "=========================================================="
echo "                   0013 BUILD-BOOK SUMMARY"
echo "=========================================================="
echo "  fens input:        $FENS ($LINES lines)"
echo "  depth:             $DEPTH"
echo "  shards:            $NSHARDS"
echo "  wall:              ${WALL}s ($(python3 -c "print(round($WALL/60,1))") min)"
echo "  merged book:       $ART/openings-77k-depth${DEPTH}.bok"
echo "  size:              $(ls -lh \"$ART/openings-77k-depth${DEPTH}.bok\" | awk '{print $5}')"
echo "  failed shards:     $fail / $NSHARDS"
echo "=========================================================="
