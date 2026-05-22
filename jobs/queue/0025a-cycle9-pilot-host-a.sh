#!/usr/bin/env bash
# id: 0025a-cycle9-pilot-host-a
# description: Cycle 9 pilot, single-host 100K @ depth 16. Generates 100K
#              WDL records labelled by the v5 NNUE (0018) — the whole point
#              of Cycle 9 is to test whether relabelling self-play data
#              with v5 (instead of the pre-Cycle-8 Linear NNUE that
#              labelled the 0010 1M) gives a strictly better training
#              corpus and therefore a better "v6" NNUE.
#
#              History: first attempt with 500K @ depth 20 measured at
#              ~150 records/h/shard, projecting 36 days for the run. That's
#              because v5 is an MLP (256-128, ~148K weights, int8 quant)
#              vs the embedded Linear NNUE (~450 weights) used in 0010, so
#              per-eval cost is ~13× higher. We kill that run and re-scope
#              this pilot:
#                * 100K records (5× smaller) at depth 16 (~4-8× faster than
#                  depth 20) → ~2 days wall.
#                * Enough signal to know if v5-labelling moves the needle;
#                  if positive, full 10M run on multi-host CPX62 cluster.
#
#              No JASS_HOST_FILTER required for single-host mode — the
#              existing runner picks this job at the next tick.
#
#              Reads:
#                /root/jass/jobs/results/0018-train-with-master-bce/
#                  artefacts.src/nnue-*-q.bin     (v5, quantised)
#
#              Writes:
#                $ART/shard-N.bin                 (4 × 25K JNNW records)
#                $ART/host-a.bin                  (100K records, merged)
#
#              Pipeline continues at:
#                0027  — train Cycle 9 NNUE on the 100K (directly)
#                0028  — bench Cycle 9 vs v5 → verdict
#
# expected_duration: ~48 hours on 4 vCPU CCX23 (~2 days).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-cycle9-pilot-host-a"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=25000           # 4 × 25 000 = 100 000 records (down from 500K).
                          # First attempt at 500K + depth 20 was throughput-
                          # limited: at ~150 rec/h/shard with v5 MLP NNUE
                          # labelling (~13× slower than the embedded Linear
                          # used in 0010), 500K would take ~36 days. 100K
                          # at depth 16 ≈ 2 days — small but enough to
                          # see whether v5-labelling moves the needle.
EVAL_DEPTH=16             # down from 20; ~4-8× faster per label with
                          # marginal quality loss vs depth-20 (the eval
                          # gain from depth-20 was modest in 0010 too).
PLAY_DEPTH=4
MAX_PLIES=200
# Seed range distinct from 0020a/b (1001-1004 / 2001-2004) and from
# this job's first throughput-limited attempt (3001-3004, killed):
# 5001-5004 so the corpus is identifiable.
SEED_BASE=5000

# v5 NNUE — same labeller chain as 0019/0022/0023 so we're always using
# the best available network rather than the pre-Cycle-8 embedded default.
NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
if [ -z "$NNUE_FILE" ] || [ ! -f "$NNUE_FILE" ]; then
    echo "ABORT: v5 NNUE not found (0018-…/nnue-*-q.bin)"
    exit 3
fi

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "filter:  ${JASS_HOST_FILTER:-(unset, OK for single-host pilot)}"
echo "nproc:   $(nproc)"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h /root | awk 'NR==2 {print $4" free of "$2}')"
echo "shards:  $NSHARDS × $PER_SHARD records (seeds $((SEED_BASE+1))-$((SEED_BASE+NSHARDS)))"
echo "NNUE:    $NNUE_FILE"
ls -lh "$NNUE_FILE"

if [ "$(nproc)" -lt 4 ]; then
    echo "ABORT: this host has only $(nproc) vCPU, expected at least 4"
    exit 3
fi

echo
echo "=== rebuilding jass (no-op if src/ unchanged) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass:    $(./build/jass --version)"

echo
echo "=== launching $NSHARDS parallel shards (NNUE=v5) ==="
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
            --nnue "$NNUE_FILE" \
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
echo
echo "=== merging this host's $NSHARDS shards into host-a.bin ==="
python3 - <<PY
import struct
from pathlib import Path

MAGIC = b"JNNW"
HEADER_SZ = 8
RECORD_SZ = 38

art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
print(f"  inputs: {[s.name for s in shards]}")

total = 0
with (art / "host-a.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
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
print(f"  merged {total} records into {art}/host-a.bin")
PY

echo
echo "=========================================================="
echo "       0025a CYCLE-9 PILOT (host A) SUMMARY"
echo "=========================================================="
echo "  host:           $(hostname)"
echo "  filter env:     ${JASS_HOST_FILTER:-UNSET}"
echo "  NNUE labeller:  $(basename "$NNUE_FILE")  (v5, Cycle 8 BCE)"
echo "  shards:         $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records"
echo "  wall:           ${WALL}s ($(python3 -c "print(round($WALL/3600,1))") h)"
echo "  per-shard rcs:"
for f in "$ART"/shard-*.result; do
    [ -f "$f" ] && echo "    $(basename $f): $(cat $f)"
done
echo "  output:         host-a.bin ($(ls -lh "$ART/host-a.bin" | awk '{print $5}'))"
echo "=========================================================="
echo
echo "Next: 0027 trains directly on host-a.bin (500K v5-labelled records);"
echo "no merge needed in single-host pilot mode. Queue 0027 — already there,"
echo "runner picks it next."
