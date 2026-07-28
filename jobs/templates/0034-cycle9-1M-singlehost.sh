#!/usr/bin/env bash
# id: 0034-cycle9-1M-singlehost
# description: Cycle 9 mini — 1M v5-labelled records sur 1× CCX23. 10×
#              plus que le pilote 100K (0025a) mais 10× moins que le
#              full 10M abandonné. Compromis: ~5-7 jours wall, ~€10.
#              Si Cycle 9 mini bat v5 d'au moins +20-30 ELO au bench
#              0036, on a validé que le v5-labelling fonctionne — on
#              peut éventuellement enchaîner sur Cycle 10 1M avec le
#              labeller v6.
#
#              Différences avec 0025a (pilote 100K) :
#                * PER_SHARD : 25000 → 250000 (×10 records).
#                * EVAL_DEPTH : 16 inchangé (compromis vitesse/qualité;
#                               passe à 18 ou 20 si 0028 montre que
#                               depth 16 sature).
#                * SEED_BASE : 9000-9003 (pas d'overlap avec 0025a's
#                              5001-5004).
#
# expected_duration: ~5-7 jours sur 4 vCPU CCX23 (depth 16 + SIMD).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0034-cycle9-1M-singlehost"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=250000
EVAL_DEPTH=16
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=9000

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
if [ -z "$NNUE_FILE" ] || [ ! -f "$NNUE_FILE" ]; then
    echo "ABORT: v5 NNUE not found (0018-…/nnue-*-q.bin)"
    exit 3
fi

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "nproc:   $(nproc)"
echo "shards:  $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records"
echo "depth:   $EVAL_DEPTH"
echo "NNUE:    $NNUE_FILE"

if [ "$(nproc)" -lt 4 ]; then
    echo "ABORT: this host has only $(nproc) vCPU"
    exit 3
fi

echo
echo "=== rebuilding jass (benefits from SIMD + accumulator now in main) ==="
cmake --build build -j"$(nproc)" 2>&1 | tail -5
echo "jass: $(./build/jass --version)"

echo
echo "=== launching $NSHARDS parallel shards (NNUE=v5, depth=$EVAL_DEPTH) ==="
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
WALL=$(( $(date +%s) - START ))
[ "$fail" -eq 0 ] || { echo "ABORT: $fail/$NSHARDS shards failed"; exit 4; }

# Canari WDL (propagation 2026-07-28). Ces templates pré-L3 ne passent pas par
# `selfplay_frontier.py merge`, où la garde est câblée pour la chaîne L3. On la
# rappelle donc ici, sur les shards produits. Elle refuse un corpus vidé de ses
# nulles — le symptôme du défaut de racine nulle d'avant 9c1d1e8e (4,8 % de
# nulles au lieu de 20,3 %), et de toute cause future qui ferait la même chose.
for _shard_data in "$ART"/shard-*.bin; do
    [ -e "$_shard_data" ] || continue
    python3 jobs/tools/assert_corpus_wdl.py --data "$_shard_data" ||
        { echo "ABORT: corpus WDL aberrant dans $_shard_data"; exit 6; }
done

echo
echo "=== merging $NSHARDS shards into cycle9-1M.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ, RECORD_SZ = 8, 38
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "cycle9-1M.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/cycle9-1M.bin")
PY

echo
echo "=========================================================="
echo "       0034 CYCLE-9 1M SINGLEHOST SUMMARY"
echo "=========================================================="
echo "  NNUE labeller:  $(basename "$NNUE_FILE")  (v5)"
echo "  depth:          $EVAL_DEPTH"
echo "  records:        $((NSHARDS * PER_SHARD))"
echo "  wall:           ${WALL}s ($(python3 -c "print(round($WALL/86400,1))")d)"
echo "  output:         cycle9-1M.bin ($(ls -lh "$ART/cycle9-1M.bin" | awk '{print $5}'))"
echo "=========================================================="
echo
echo "Next: 0035-train-cycle9-1M, then 0036-bench-cycle9-1M-vs-v5."
