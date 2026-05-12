#!/usr/bin/env bash
# id: 0009-rate-test-bigbox
# description: 30-min smoke test on the freshly bootstrapped CCX63
#              (48 vCPU AMD EPYC-Milan). Validates that the per-CPU
#              rate measured on the CCX 16GB (0.547 r/s/CPU) holds
#              when scaled to 48 shards in parallel — i.e. no memory
#              bandwidth or scheduler contention. If the rate per CPU
#              is within ~10% of 0.547, we're cleared to commit to
#              the 10M run.
# expected_duration: ~30 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0009-rate-test-bigbox"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=48
PER_SHARD=1000           # small workload to keep the smoke under 30 min
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "nproc:  $(nproc)"
echo "cpu:    $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mem:    $(free -h | awk '/^Mem:/ {print $2}')"
echo "load:   $(cut -d' ' -f1-3 /proc/loadavg)"
echo "jass:   $(./build/jass --version 2>/dev/null || echo 'no --version')"

if [ "$(nproc)" -lt 32 ]; then
    echo "WARN: this host has only $(nproc) vCPU — meant for CCX63 (48 vCPU)"
fi

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
done
echo "  $NSHARDS shards launched"

echo
echo "=== waiting on all shards ==="
fail=0
for i in "${!pids[@]}"; do
    p="${pids[$i]}"
    shard=$((i + 1))
    if ! wait "$p"; then
        rc=$?
        echo "  shard $shard FAILED rc=$rc"
        fail=$((fail + 1))
    fi
done
END=$(date +%s)
WALL=$((END - START))

echo
echo "=== per-shard timing (rc / seconds), sorted by duration ==="
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] || continue
    shard=$(basename "$f" | sed 's/shard-\(.*\)\.result/\1/')
    echo "  shard $shard: $(cat "$f")"
done | sort -k4 -n

if [ "$fail" -gt 0 ]; then
    echo
    echo "=== $fail shard(s) failed ==="
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

TOTAL_RECORDS=$((PER_SHARD * NSHARDS))
RPS=$(python3 -c "print(round($TOTAL_RECORDS / $WALL, 3))")
RPS_CPU=$(python3 -c "print(round($TOTAL_RECORDS / $WALL / $NSHARDS, 4))")
EXTRAP_10M_HRS=$(python3 -c "print(round(10000000 / max($TOTAL_RECORDS / $WALL, 0.0001) / 3600, 2))")
EXTRAP_10M_DAYS=$(python3 -c "print(round(10000000 / max($TOTAL_RECORDS / $WALL, 0.0001) / 3600 / 24, 2))")

echo
echo "=========================================================="
echo "                  RATE SUMMARY"
echo "=========================================================="
echo "  total records      $TOTAL_RECORDS"
echo "  wall seconds       $WALL"
echo "  records/sec total  $RPS"
echo "  records/sec/CPU    $RPS_CPU      (CCX23 ref: 0.547)"
echo
echo "  10M extrapolation  $EXTRAP_10M_HRS h  =  $EXTRAP_10M_DAYS days"
echo "=========================================================="
echo
echo "Decision:"
echo "  * if records/sec/CPU is within 0.45-0.65 -> SCALING OK,"
echo "    proceed to queue 0010-gen-data-depth20-10M-bigbox"
echo "  * if records/sec/CPU < 0.40 -> investigate (memory bw,"
echo "    NUMA, hyperthreading) before committing to the 10M run"
