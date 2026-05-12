#!/usr/bin/env bash
# id: 0005-rate-test-depth20-v2
# description: depth-20 rate-test, retry of 0002. 0002 was reaped as
#              failed by the runner due to the setsid double-fork bug
#              (fixed in this same PR) — the shards were actually
#              still computing fine. Same workload (4 shards × 5000
#              records @ depth 20) but with shard-failure-tolerant
#              wait, per-shard timing, and no `set -e` killing the
#              whole script if a single shard fails.
# expected_duration: ~15-25 min on a 4 vCPU host
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0005-rate-test-depth20-v2"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

PER_SHARD=5000
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200
NSHARDS=4

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "cpu:    $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mem:    $(free -h | awk '/^Mem:/ {print $2}')"
echo "jass:   $(./build/jass --version 2>/dev/null || echo '(no --version)')"

echo
echo "=== launching $NSHARDS parallel shards (per_shard=$PER_SHARD depth=$EVAL_DEPTH) ==="
START=$(date +%s)
pids=()
for shard in $(seq 1 $NSHARDS); do
    (
        START_SH=$(date +%s)
        ./build/jass --gen-data-wdl \
            "$PER_SHARD" \
            "$ART/shard-$shard.bin" \
            "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAX_PLIES" "$shard" \
            > "$ART/shard-$shard.log" 2>&1
        rc=$?
        END_SH=$(date +%s)
        echo "$rc $((END_SH - START_SH))" > "$ART/shard-$shard.result"
        exit $rc
    ) &
    pids+=($!)
    echo "  shard $shard launched as pid $!"
done

echo
echo "=== waiting on all shards (no errexit, capture per-shard rc) ==="
fail=0
for i in "${!pids[@]}"; do
    p="${pids[$i]}"
    shard=$((i + 1))
    if wait "$p"; then
        echo "  shard $shard: OK"
    else
        rc=$?
        echo "  shard $shard: FAILED rc=$rc"
        fail=$((fail + 1))
    fi
done
END=$(date +%s)
WALL=$((END - START))

echo
echo "=== shard sizes ==="
ls -la "$ART"
echo
echo "=== per-shard result lines (rc / seconds) ==="
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] || continue
    echo "  $f: $(cat "$f")"
done

if [ "$fail" -gt 0 ]; then
    echo
    echo "=== $fail shard(s) failed — first 50 lines of each failing shard log ==="
    for i in "${!pids[@]}"; do
        shard=$((i + 1))
        rc=$(awk '{print $1}' "$ART/shard-$shard.result" 2>/dev/null || echo "?")
        if [ "$rc" != "0" ]; then
            echo "--- shard $shard (rc=$rc) ---"
            head -50 "$ART/shard-$shard.log" || true
        fi
    done
    echo
    echo "=== exiting with non-zero (rate metrics undefined) ==="
    exit 2
fi

echo
echo "=== merging shards ==="
python3 - <<PY
import glob, struct, sys, os
paths = sorted(glob.glob("$ART/shard-*.bin"))
total = 0
with open("$ART/depth20-rate-test.bin", "wb") as out:
    out.write(b"JNNW"); out.write(struct.pack("<I", 0))
    for p in paths:
        raw = open(p, "rb").read()
        if raw[:4] != b"JNNW":
            sys.exit(f"{p}: bad magic")
        n = struct.unpack_from("<I", raw, 4)[0]
        if len(raw) != 8 + n * 38:
            sys.exit(f"{p}: size mismatch (header says {n}, file is {len(raw)} bytes)")
        out.write(raw[8:]); total += n
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} records to depth20-rate-test.bin ({os.path.getsize('$ART/depth20-rate-test.bin')} bytes)")
PY

echo
TOTAL_RECORDS=$((PER_SHARD * NSHARDS))
echo "=== rate summary ==="
echo "total records:    $TOTAL_RECORDS"
echo "wall seconds:     $WALL"
echo "wall hours:       $(python3 -c "print(round($WALL/3600, 2))")"
echo "records/sec:      $(python3 -c "print(round($TOTAL_RECORDS / $WALL, 2))")"
echo "records/sec/cpu:  $(python3 -c "print(round($TOTAL_RECORDS / $WALL / $NSHARDS, 2))")"
echo "extrapolated 200k wall hours:  $(python3 -c "print(round(200000 / $TOTAL_RECORDS * $WALL / 3600, 2))")"
echo "extrapolated 1M   wall hours:  $(python3 -c "print(round(1000000 / $TOTAL_RECORDS * $WALL / 3600, 2))")"
echo "extrapolated 10M  wall hours:  $(python3 -c "print(round(10000000 / $TOTAL_RECORDS * $WALL / 3600, 2))")"
