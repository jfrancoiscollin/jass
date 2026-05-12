#!/usr/bin/env bash
# id: 0010-gen-data-depth20-1M-smallbox
# description: first NNUE training dataset, scaled for the CCX23 we
#              already own (4 vCPU AMD EPYC-Milan). 4 shards × 250 000
#              records = 1 000 000 records @ depth 20. At the rate
#              measured in 0007 (0.547 r/s/CPU), ≈ 5.3 days wall.
#
#              Starts by killing any 0009 orphans from the bigbox-
#              targeted job CCX23 wrongly picked before its timer was
#              disabled.
# expected_duration: ~5.3 days on 4 vCPU
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

echo "=== killing any 0009-rate-test-bigbox orphans (48 shards launched on 4 vCPU = thrashing) ==="
echo "--- pre-kill matches ---"
pgrep -af 'jobs/(queue|results)/0009-' || echo "(no orphans)"
pkill -TERM -f 'jobs/(queue|results)/0009-' 2>/dev/null && echo "sent SIGTERM" || echo "(nothing to TERM)"
sleep 3
pkill -KILL -f 'jobs/(queue|results)/0009-' 2>/dev/null && echo "sent SIGKILL" || echo "(nothing to KILL)"
echo "--- post-kill matches ---"
pgrep -af 'jobs/(queue|results)/0009-' || echo "(clear)"

echo
echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "cpu:     $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2{print $4 " free of " $2}')"
echo "load:    $(cut -d' ' -f1-3 /proc/loadavg)"
echo "jass:    $(./build/jass --version 2>/dev/null || echo '(no --version)')"

NSHARDS=4
PER_SHARD=250000
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200

if [ "$(nproc)" -lt 4 ]; then
    echo "ABORT: this host has only $(nproc) vCPU, expected at least 4"
    exit 3
fi
if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 10 ]; then
    echo "ABORT: less than 10 GB free on /, refusing to start a 5-day job"
    exit 3
fi

echo
echo "=== plan ==="
echo "shards:           $NSHARDS"
echo "records/shard:    $PER_SHARD"
echo "total records:    $((PER_SHARD * NSHARDS))"
echo "expected size:    ~$((PER_SHARD * NSHARDS * 38 / 1024 / 1024)) MB raw across $NSHARDS .bin files"
echo "eval depth:       $EVAL_DEPTH"
echo "play depth:       $PLAY_DEPTH"
echo "max plies/game:   $MAX_PLIES"
echo "rate ref:         0.547 records/sec/CPU on this CCX23 (from 0007)"
echo "ETA:              ~$(python3 -c "print(round($PER_SHARD * $NSHARDS / 0.547 / $NSHARDS / 86400, 2))") days at the reference rate"

echo
echo "=== launching $NSHARDS parallel shards ==="
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
    echo "=== $fail shard(s) failed — first 50 lines of each failing log ==="
    for i in "${!pids[@]}"; do
        shard=$((i + 1))
        rc=$(awk '{print $1}' "$ART/shard-$shard.result" 2>/dev/null || echo "?")
        if [ "$rc" != "0" ]; then
            echo "--- shard $shard (rc=$rc) ---"
            head -50 "$ART/shard-$shard.log" || true
        fi
    done
    exit 2
fi

echo
echo "=== merging shards into one JNNW file ==="
python3 - <<PY
import glob, struct, sys, os
paths = sorted(glob.glob("$ART/shard-*.bin"))
total = 0
with open("$ART/depth20-1M.bin", "wb") as out:
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
print(f"merged {total} records to depth20-1M.bin ({os.path.getsize('$ART/depth20-1M.bin')} bytes)")
PY

TOTAL_RECORDS=$((PER_SHARD * NSHARDS))
echo
echo "=========================================================="
echo "                  1M GEN-DATA SUMMARY"
echo "=========================================================="
echo "  total records       $TOTAL_RECORDS"
echo "  wall seconds        $WALL"
echo "  wall hours          $(python3 -c "print(round($WALL/3600, 2))")"
echo "  wall days           $(python3 -c "print(round($WALL/86400, 2))")"
echo "  records/sec total   $(python3 -c "print(round($TOTAL_RECORDS / $WALL, 3))")"
echo "  records/sec/CPU     $(python3 -c "print(round($TOTAL_RECORDS / $WALL / $NSHARDS, 4))")"
echo "  failed shards       $fail / $NSHARDS"
echo "=========================================================="
echo
echo "Merged dataset:        artefacts/depth20-1M.bin (~$((TOTAL_RECORDS * 38 / 1024 / 1024 + 1)) MB)"
echo "Individual shards:     artefacts/shard-{1..$NSHARDS}.bin"
echo "Next:                  train HalfMen-v1 on depth20-1M.bin"
