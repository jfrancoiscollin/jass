#!/usr/bin/env bash
# id: 0010-gen-data-depth20-10M-bigbox
# description: full-scale depth-20 self-play data generation for the
#              first NNUE training set. 48 shards × 208334 records =
#              10_000_032 records on CCX63. Each shard committed as
#              its own .bin via the runner's artefacts mechanism
#              (~7.9 MB each, well under the 50 MB cap). NO merge
#              step (10M × 38 B = 380 MB > git cap; the user merges
#              locally if needed).
# expected_duration: ~4-5 days on CCX63 at the 0009-validated rate
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0010-gen-data-depth20-10M-bigbox"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=48
PER_SHARD=208334            # 48 × 208334 = 10_000_032
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "cpu:     $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2{print $4 " free of " $2}')"
echo "load:    $(cut -d' ' -f1-3 /proc/loadavg)"
echo "jass:    $(./build/jass --version 2>/dev/null || echo '(no --version)')"

if [ "$(nproc)" -lt 32 ]; then
    echo "ABORT: this host has only $(nproc) vCPU — meant for CCX63 (48 vCPU)"
    exit 3
fi
if [ "$(df -BG --output=avail / | tail -1 | tr -dc '0-9')" -lt 50 ]; then
    echo "ABORT: less than 50 GB free on /, refusing to start a multi-day job"
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
echo "rate ref (CCX23): 0.547 records/sec/CPU"
echo "ETA:              ~$(python3 -c "print(round($PER_SHARD * $NSHARDS / 0.547 / $NSHARDS / 3600 / 24, 2))") days at the reference rate"

echo
echo "=== launching $NSHARDS parallel shards ==="
START=$(date +%s)
pids=()
for shard in $(seq 1 $NSHARDS); do
    (
        START_SH=$(date +%s)
        ./build/jass --gen-data-wdl \
            "$PER_SHARD" \
            "$ART/shard-$(printf '%02d' "$shard").bin" \
            "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAX_PLIES" "$shard" \
            > "$ART/shard-$(printf '%02d' "$shard").log" 2>&1
        rc=$?
        END_SH=$(date +%s)
        echo "$rc $((END_SH - START_SH))" > "$ART/shard-$(printf '%02d' "$shard").result"
        exit $rc
    ) &
    pids+=($!)
done
echo "  $NSHARDS shards launched. Heartbeats every 5 min in progress.json."

echo
echo "=== waiting on all shards (no errexit) ==="
fail=0
for i in "${!pids[@]}"; do
    p="${pids[$i]}"
    shard=$((i + 1))
    if wait "$p"; then
        :
    else
        rc=$?
        echo "  shard $(printf '%02d' "$shard"): FAILED rc=$rc"
        fail=$((fail + 1))
    fi
done
END=$(date +%s)
WALL=$((END - START))

echo
echo "=== shard outcomes (rc / seconds), sorted by duration ==="
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] || continue
    s=$(basename "$f" | sed 's/shard-\(.*\)\.result/\1/')
    echo "  shard $s: $(cat "$f")"
done | sort -k4 -n

echo
echo "=== shard sizes ==="
ls -la "$ART"/shard-*.bin 2>/dev/null | awk '{print $9, $5}' | column -t

TOTAL_RECORDS=$((PER_SHARD * NSHARDS))
RPS=$(python3 -c "print(round($TOTAL_RECORDS / $WALL, 3))")
RPS_CPU=$(python3 -c "print(round($TOTAL_RECORDS / $WALL / $NSHARDS, 4))")
TOTAL_BIN_BYTES=$((TOTAL_RECORDS * 38 + NSHARDS * 8))

echo
echo "=========================================================="
echo "                  10M GEN-DATA SUMMARY"
echo "=========================================================="
echo "  total records       $TOTAL_RECORDS"
echo "  raw bytes (sum)     $TOTAL_BIN_BYTES  (~$((TOTAL_BIN_BYTES / 1024 / 1024)) MB)"
echo "  wall seconds        $WALL"
echo "  wall hours          $(python3 -c "print(round($WALL/3600, 2))")"
echo "  wall days           $(python3 -c "print(round($WALL/86400, 2))")"
echo "  records/sec total   $RPS"
echo "  records/sec/CPU     $RPS_CPU"
echo "  failed shards       $fail / $NSHARDS"
echo "=========================================================="
echo
echo "Each shard.bin is committed individually under artefacts/."
echo "To rebuild a single 10M JNNW file locally:"
echo "  python3 tools/merge_shards.py jobs/results/0010-gen-data-depth20-10M-bigbox/artefacts/shard-*.bin -o depth20-10M.bin"
echo "  (helper not yet committed; trivially derived from 0007's inline merge)"

if [ "$fail" -gt 0 ]; then
    echo
    echo "WARN: $fail shard(s) failed — usable record count is"
    echo "      ~$((TOTAL_RECORDS - fail * PER_SHARD)) instead of $TOTAL_RECORDS"
    exit 2
fi
