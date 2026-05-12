#!/usr/bin/env bash
# id: 0002-rate-test-depth20
# description: small depth-20 gen-data run (5k records × 4 parallel
#              shards = 20k total) to measure the actual records/sec
#              rate on this host. Drives the sizing of the next
#              full-scale depth-20 dataset.
# expected_duration: ~15-25 min on a CCX23
set -euo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0002-rate-test-depth20"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

PER_SHARD=5000
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200

echo "=== launching 4 parallel shards (per_shard=$PER_SHARD depth=$EVAL_DEPTH) ==="
START=$(date +%s)
pids=()
for shard in 1 2 3 4; do
    (
        START_SH=$(date +%s)
        ./build/jass --gen-data-wdl \
            "$PER_SHARD" \
            "$ART/shard-$shard.bin" \
            "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAX_PLIES" "$shard" \
            > "$ART/shard-$shard.log" 2>&1
        END_SH=$(date +%s)
        echo "shard $shard: $((END_SH - START_SH))s"
    ) &
    pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
END=$(date +%s)
WALL=$((END - START))

echo
echo "=== shard sizes ==="
ls -la "$ART"
echo
echo "=== merge ==="
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
            sys.exit(f"{p}: size mismatch")
        out.write(raw[8:]); total += n
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} records to depth20-rate-test.bin ({os.path.getsize('$ART/depth20-rate-test.bin')} bytes)")
PY

echo
TOTAL_RECORDS=$((PER_SHARD * 4))
echo "=== rate summary ==="
echo "total records:    $TOTAL_RECORDS"
echo "wall seconds:     $WALL"
echo "wall hours:       $(python3 -c "print(round($WALL/3600, 2))")"
echo "records/sec:      $(python3 -c "print(round($TOTAL_RECORDS / $WALL, 2))")"
echo "records/sec/cpu:  $(python3 -c "print(round($TOTAL_RECORDS / $WALL / 4, 2))")"
echo "extrapolated 200k wall hours:  $(python3 -c "print(round(200000 / $TOTAL_RECORDS * $WALL / 3600, 2))")"
echo "extrapolated 1M   wall hours:  $(python3 -c "print(round(1000000 / $TOTAL_RECORDS * $WALL / 3600, 2))")"
