#!/usr/bin/env bash
# id: 0025a-cycle9-pilot-host-a
# description: Cycle 9 pilot, single-host 500K. Generates 500K WDL records
#              labelled by the v5 NNUE (0018) — this is the whole point
#              of Cycle 9: the 0010 1M dataset was labelled by the
#              pre-Cycle-8 NNUE, so training a new model on it can't
#              improve beyond the limits of that labeller. By labelling
#              with v5 (Cycle 8 BCE, +304 ELO vs handcrafted), we should
#              get a strictly better training corpus and, after retraining,
#              a "v6" NNUE that exceeds v5.
#
#              Originally designed as 500K-on-host-A of a 1M 2-host pilot
#              (with 0025b, 0026 doing host B + merge). The 2nd CCX23 isn't
#              available yet, so we de-risk by running the 500K alone on the
#              existing host and skipping the merge — 0027 trains directly
#              on this output. If a 2nd host comes online later, queue an
#              0025c that mirrors this one with seeds 4001-4004 and a fresh
#              merge job, retrain.
#
#              At ~5 CPU-sec per record on 4 vCPU CCX23, 500K = ~175 CPU-hours
#              / 4 cores ÷ 4 shards ≈ ~67-72 hours wall (~3 days).
#
#              No JASS_HOST_FILTER required for single-host mode — the
#              existing runner picks this job at the next tick.
#
#              Reads:
#                /root/jass/jobs/results/0018-train-with-master-bce/
#                  artefacts.src/nnue-*-q.bin     (v5, quantised)
#
#              Writes:
#                $ART/shard-N.bin                 (4 × 125K JNNW records)
#                $ART/host-a.bin                  (500K records, merged)
#
#              Pipeline continues at:
#                0027  — train Cycle 9 NNUE on the 500K (directly)
#                0028  — bench Cycle 9 vs v5 → verdict
#
# expected_duration: ~67-72 hours on 4 vCPU CCX23 (~3 days).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-cycle9-pilot-host-a"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=125000          # 4 × 125 000 = 500 000 records, half of the 1M pilot
EVAL_DEPTH=20             # same as 0010 / 0020; depth-20 labels
PLAY_DEPTH=4
MAX_PLIES=200
# Seed range distinct from 0020a/b (1001-1004 / 2001-2004): 3001-3004
# guarantees no overlap with the existing depth-20 corpus or with
# 0025b's seeds (4001-4004), so the 1M dataset is fully independent.
SEED_BASE=3000

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
