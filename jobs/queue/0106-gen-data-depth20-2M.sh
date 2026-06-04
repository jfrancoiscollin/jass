#!/usr/bin/env bash
# id: 0106-gen-data-depth20-2M
# description: Première itération "cycle Stockfish" — gen 2M positions
# self-play, labels WDL au depth 20, étiqueteur = v15 128-64 quantisé.
#
# Phase 2 du plan stratégique : booster l'ELO de 128-64 via plus de
# data plus profonde. Master (1.6M) + ce 2M → 3.6M training set pour
# v16.
#
# Sizing : 8 shards × 250k records sur 8 vCPU ≈ 8 jours wall (~250k
# r/jour/host à depth 20, extrapolé de 0010 et 0030).
#
# IMPORTANT : ce job bloque le runner pour ~8 jours. Pas de jobs
# concurrents sur ce host pendant ce temps. Si besoin de pivoter,
# utiliser jobs/state/kill-in-flight pour l'arrêter proprement.
#
# Pipeline suite :
#   0106 — gen 2M positions depth 20
#   0107 — train v16 128-64 sur master+2M
#   0108 — bench v16 vs v15 + vs Scan (verdict ELO)
#
# expected_duration: ~8 jours wall sur 8 vCPU
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0106-gen-data-depth20-2M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "cpu:     $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mem:     $(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2{print $4 " free of " $2}')"
echo "load:    $(cut -d' ' -f1-3 /proc/loadavg)"

NSHARDS=$(nproc)
TOTAL_RECORDS=2000000
PER_SHARD=$(( (TOTAL_RECORDS + NSHARDS - 1) / NSHARDS ))
EVAL_DEPTH=20
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=10600

if [ "$NSHARDS" -lt 4 ]; then
    echo "ABORT: need >= 4 vCPU, host has $NSHARDS"; exit 3
fi

NNUE_FILE=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -f "$NNUE_FILE" ] || { echo "ABORT: no v15 128-64 weights"; exit 3; }
echo "labeller: $NNUE_FILE"

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo
echo "=== build prod ==="
if [ ! -x ./build/jass ]; then
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
fi
cmake --build build -j"$NSHARDS" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

echo
echo "=== launching $NSHARDS shards × $PER_SHARD records (= $TOTAL_RECORDS total) ==="
echo "    eval depth: $EVAL_DEPTH  play depth: $PLAY_DEPTH  max plies: $MAX_PLIES"
echo "    seed base:  $SEED_BASE   labeller: $(basename "$NNUE_FILE")"
echo

pids=()
START_ALL=$(date +%s)
for shard in $(seq 0 $((NSHARDS - 1))); do
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
        echo "$rc $(( $(date +%s) - START_SH ))" > "$ART/shard-$shard.result"
        exit $rc
    ) &
    pids+=($!)
    echo "  shard $shard launched as pid $! (seed $seed)"
done

echo
echo "=== waiting on all shards ==="
fail=0
for p in "${pids[@]}"; do
    if ! wait "$p"; then fail=$((fail + 1)); fi
done
DUR=$(( $(date +%s) - START_ALL ))
echo
echo "=== all shards done in ${DUR}s ($(( DUR / 3600 ))h $(( (DUR % 3600) / 60 ))min). failures: $fail ==="

if [ "$fail" -gt 0 ]; then
    echo "FAIL: $fail shards failed"
    tail -20 "$ART"/shard-*.log
    exit 6
fi

# Merge shards
echo
echo "=== merging shards → gen-2M-depth20.bin ==="
OUT_FILE="$ART/gen-2M-depth20.bin"
python3 - <<EOF > "$ART/merge.log" 2>&1
import struct, sys
from pathlib import Path
shards = sorted(Path("$ART").glob("shard-*.bin"))
total = 0
header_size = 8
record_size = 38
with open("$OUT_FILE", "wb") as out:
    out.write(struct.pack("<II", 0, 0))  # placeholder header
    for sh in shards:
        raw = sh.read_bytes()
        n = struct.unpack_from('<I', raw, 4)[0]
        out.write(raw[header_size:header_size + n * record_size])
        total += n
        print(f"  {sh.name}: {n} records")
    out.seek(0)
    out.write(struct.pack("<II", 0xCAFE0001, total))
print(f"total merged: {total}")
EOF
cat "$ART/merge.log"

# Summary
echo
echo "=========================================================="
echo "       0106 GEN DATA SUMMARY"
echo "=========================================================="
ls -la "$OUT_FILE"
echo
echo "Per-shard timing :"
for shard in $(seq 0 $((NSHARDS - 1))); do
    if [ -f "$ART/shard-$shard.result" ]; then
        read rc dur < "$ART/shard-$shard.result"
        echo "  shard $shard: rc=$rc duration=${dur}s ($(( dur / 3600 ))h $(( (dur % 3600) / 60 ))min)"
    fi
done
echo
echo "Total wall: $(( DUR / 3600 ))h $(( (DUR % 3600) / 60 ))min"
echo "Output    : $OUT_FILE"
echo "Next step : 0107 train v16 128-64 sur master + ce 2M"
echo "=========================================================="
