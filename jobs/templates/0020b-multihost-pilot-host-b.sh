#!/usr/bin/env bash
# id: 0020b-multihost-pilot-host-b
# description: Multi-host pilot, host B's half. Validates that two
#              CCX23 instances of the GitOps runner can run in parallel
#              without racing on the same job (each one picks only the
#              scripts matching its JASS_HOST_FILTER prefix).
#
#              This is the SETUP-VALIDATION job — not the real Cycle 9
#              gen-data run. It produces only 100K records (~half a day
#              on 4 vCPU at the rate measured by 0010) so we can spin
#              up the infrastructure, watch both hosts work in parallel,
#              and verify the merge step before committing to a full
#              1M or 10M Cycle 9 run.
#
#              Host A is expected to:
#                * have JASS_HOST_FILTER=0020b- in its systemd env
#                * pick THIS script (and not its sibling 0020b-…)
#                * generate 100K records with seed 1001-1004 across 4 shards
#                * write to its own result dir (no conflict with host B)
#
#              After both 0020a and 0020b finalize, queue 0021-merge-…
#              to combine the two halves into a single 200K dataset.
# expected_duration: ~12-15 hours on 4 vCPU CCX23
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0020b-multihost-pilot-host-b"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=25000          # 4 × 25 000 = 100 000 records, ~12-15h on 4 vCPU
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200
# Distinct seed range from host B (1001-1004 vs 2001-2004) so the two
# halves of the 200K dataset don't overlap.
SEED_BASE=2000

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "filter:  ${JASS_HOST_FILTER:-(unset, should be '0020b-')}"
echo "nproc:   $(nproc)"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h /root | awk 'NR==2 {print $4" free of "$2}')"
echo "shards:  $NSHARDS x $PER_SHARD records (seeds $((SEED_BASE+1))-$((SEED_BASE+NSHARDS)))"

if [ "$(nproc)" -lt 4 ]; then
    echo "ABORT: this host has only $(nproc) vCPU, expected at least 4"
    exit 3
fi

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass: $(./build/jass --version)"

echo
echo "=== launching $NSHARDS parallel shards ==="
START=$(date +%s)
pids=()
for shard in $(seq 1 $NSHARDS); do
    seed=$((SEED_BASE + shard))
    (
        START_SH=$(date +%s)
        ./build/jass --gen-data-wdl \
            "$PER_SHARD" \
            "$ART/shard-$shard.bin" \
            "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAX_PLIES" "$seed" \
            > "$ART/shard-$shard.log" 2>&1
        rc=$?
        END_SH=$(date +%s)
        echo "$rc $((END_SH - START_SH))" > "$ART/shard-$shard.result"
        exit $rc
    ) &
    pids+=($!)
    echo "  shard $shard launched as pid $! (seed $seed)"
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

if [ "$fail" -gt 0 ]; then
    echo "ABORT: $fail / $NSHARDS shards failed"
    exit 4
fi

# Merge this host's 4 shards into a single per-host blob.
# 0021 will combine host B's + host B's blobs into the final 200K dataset.
echo
echo "=== merging this host's $NSHARDS shards into host-b.bin ==="
python3 - <<PY
import struct, sys
from pathlib import Path

MAGIC = b"JNNW"
HEADER_SZ = 8
RECORD_SZ = 38

art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
print(f"  inputs: {[s.name for s in shards]}")

total = 0
with (art / "host-b.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))  # placeholder
    for s in shards:
        raw = s.read_bytes()
        assert raw[:4] == MAGIC, f"{s}: bad magic"
        cnt = struct.unpack_from("<I", raw, 4)[0]
        expected = HEADER_SZ + cnt * RECORD_SZ
        assert len(raw) == expected, f"{s}: bad size"
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"  merged {total} records into {art}/host-b.bin")
PY

echo
echo "=========================================================="
echo "       0020a MULTI-HOST PILOT (host B) SUMMARY"
echo "=========================================================="
echo "  host:           $(hostname)"
echo "  filter env:     ${JASS_HOST_FILTER:-UNSET}"
echo "  shards:         $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records"
echo "  wall:           ${WALL}s ($(python3 -c "print(round($WALL/3600,1))") h)"
echo "  per-shard rcs:"
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] && echo "    $(basename $f): $(cat $f)"
done
echo "  output:         host-b.bin ($(ls -lh "$ART/host-b.bin" | awk '{print $5}'))"
echo "=========================================================="
echo
echo "Next step: wait for 0020b (host B) to finish on its host."
echo "Then queue 0021-merge-multihost-shards to combine host-b.bin"
echo "and host-b.bin into a single 200K training blob."
