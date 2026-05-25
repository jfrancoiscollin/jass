#!/usr/bin/env bash
# id: 0045-quiet-pv-extract-scaleup
# description: Conditional follow-up to 0043. À ACTIVER (move templates→queue)
#              SEULEMENT si 0043 sort un verdict strong/solid gain
#              (rate vs v5 d10 >= 0.52). Sinon : NE PAS activer, on
#              bascule sur Phase 0b (master volume) per ROADMAP.md.
#
#              Combine les deux leviers data-side validés :
#                * --quiet-only        (filtrage quiétude, PR #81)
#                * --pv-extract 3      (multi-extraction PV, PR #84)
#
#              Volume cible : 500K records (vs 200K pour le pilote 0043).
#              Coût attendu fortement réduit par --pv-extract (~×3 labels
#              par root search) → gen-data ~5-8h plutôt qu'~15-20h naïf.
#
# expected_duration: ~10-14h sur 4 vCPU CCX23 :
#                    * gen-data 500K @ depth 16 avec quiet+pv-extract (~5-8h)
#                    * train (~2h)
#                    * bench (~1h)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0045-quiet-pv-extract-scaleup"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=125000          # 4 × 125K = 500K records. ~2.5× le pilote 0043.
EVAL_DEPTH=16             # identique à 0043 (variables testées = volume
                          # × pv-extract, pas la depth).
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=21000           # distinct des seeds 0043 (20001-20004)
PV_EXTRACT=3              # cf. PR #84 — ~2.9× speedup mesuré.

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$NNUE_FILE" ] && [ -f "$NNUE_FILE" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "shards: $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records @ depth $EVAL_DEPTH"
echo "filters: --quiet-only --pv-extract $PV_EXTRACT"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== Phase 0a : gen-data 500K WITH --quiet-only --pv-extract $PV_EXTRACT, v5 labeller ==="
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
            --quiet-only \
            --pv-extract "$PV_EXTRACT" \
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
WALL_GEN=$(( $(date +%s) - START ))
[ "$fail" -eq 0 ] || { echo "ABORT: $fail/$NSHARDS shards failed"; exit 4; }

echo
echo "=== merging into quiet-pv-500K.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ, RECORD_SZ = 8, 38
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "quiet-pv-500K.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/quiet-pv-500K.bin")
PY

DATASET="$ART/quiet-pv-500K.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
[ -f "$MASTER" ] || { echo "ABORT: master $MASTER not found"; exit 3; }

echo
echo "=== Phase 0b : train v5-recipe sur dataset quiet+pv-extract ==="
if ! python3 -c "import torch, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages --no-cache-dir --quiet \
            numpy torch --index-url https://download.pytorch.org/whl/cpu && break
        sleep 10
    done
    rm -rf "$PIP_SCRATCH"
fi

START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$DATASET" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  2000000 \
    --archs               64-32 128-64 256-128 512-256 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

BEST_ARCH=$(python3 -c "
import json
with open('$ART/summary.json') as f: s = json.load(f)
print(sorted(s.items(), key=lambda kv: kv[1]['val_mse'])[0][0])
")
BEST_BIN="$ART/nnue-${BEST_ARCH}.bin"
QUANT_OUT="$ART/nnue-${BEST_ARCH}-q.bin"

python3 tools/quantize_mlp.py --in "$BEST_BIN" --data "$DATASET" --out "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"

echo
echo "=== Phase 0c : bench quiet+pv-trained vs v5 ==="
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V5" 6 3  2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0045 QUIET + PV-EXTRACT SCALEUP VERDICT"
echo "=========================================================="
echo "  gen wall:        ${WALL_GEN}s ($(python3 -c "print(round($WALL_GEN/3600,1))")h)"
echo "  train wall:      ${TRAIN_SEC}s"
echo "  best arch:       $BEST_ARCH"
echo "  records:         $((NSHARDS * PER_SHARD)) (quiet + pv-extract $PV_EXTRACT)"
echo
echo "  vs handcrafted:    rate=$RATE_HC"
echo "  vs v5 (depth 6):   rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):  rate=$RATE_V5_D10"
echo
echo "  References :"
echo "    v5 reference vs handcrafted: 0.852"
echo "    0043 200K quiet-only vs v5 d10: <CF VERDICT 0043>"
echo
echo "  Decision :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.60) }'; then
    echo "    BIG WIN — quiet+pv combo + volume domine. Adopter comme"
    echo "    default pour tout futur gen-data. Considérer un run 1M."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    SOLID WIN — gain net du combo + volume. Ship comme v6."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    MARGINAL — le volume n'ajoute pas grand chose au-delà du"
    echo "    quiet filter 200K. Passer à Phase 0b (master) ou Phase 1+."
else
    echo "    REGRESSION — bug ou interaction quiet × pv-extract. Debug."
fi
echo "=========================================================="
