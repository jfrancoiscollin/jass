#!/usr/bin/env bash
# id: 0039-cycle9-1M-depth10-singlehost
# description: Test l'hypothèse Stockfish/Leela : "label dataset @ low
#              depth + WDL signal bat label @ high depth en volume
#              équivalent". Mirror exact de 0034 SAUF EVAL_DEPTH=10
#              au lieu de 16.
#
#              Si le NNUE entraîné sur ce corpus depth-10 (0040) bat
#              ou égale celui entraîné sur le corpus depth-16 (0035),
#              on a un free lunch méthodologique : ~2-3× de débit
#              gen-data à qualité label équivalente. Énorme pour les
#              futurs cycles (10M, 100M devient envisageable).
#
#              Si le depth-10 perd nettement (>20 ELO) : la précision
#              du score par position compte plus en draughts qu'en
#              chess (horizon effect plus marqué), on reste à depth 16+.
#
#              Coût : ~€2-3, ~12-15h wall sur 1× CCX23 avec le binaire
#              SIMD+accumulator de main.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0039-cycle9-1M-depth10-singlehost"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=250000
EVAL_DEPTH=10               # ← LA variable testée
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=10000             # distinct de 0034 (9001-9004)

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$NNUE_FILE" ] && [ -f "$NNUE_FILE" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host:  $(hostname)  nproc: $(nproc)"
echo "shards: $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) @ depth $EVAL_DEPTH"
echo "NNUE:   $NNUE_FILE"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

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

fail=0
for p in "${pids[@]}"; do wait "$p" || fail=$((fail + 1)); done
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

echo "=== merge into cycle9-1M-depth10.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ, RECORD_SZ = 8, 38
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "cycle9-1M-depth10.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/cycle9-1M-depth10.bin")
PY

echo
echo "=========================================================="
echo "       0039 CYCLE-9 1M @ DEPTH 10 SUMMARY"
echo "=========================================================="
echo "  depth:      $EVAL_DEPTH (vs 16 dans 0034 — variable testée)"
echo "  records:    $((NSHARDS * PER_SHARD))"
echo "  wall:       ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  output:     cycle9-1M-depth10.bin ($(ls -lh "$ART/cycle9-1M-depth10.bin" | awk '{print $5}'))"
echo "=========================================================="
echo
echo "Next: 0040-train, puis 0041-bench-depth10-vs-v5."
