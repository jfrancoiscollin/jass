#!/usr/bin/env bash
# id: 0043-quiet-filter-experiment
# description: Phase 0 du ROADMAP post-bibliographie. Régénère un
#              corpus self-play AVEC `--quiet-only` (skip les
#              positions tactiques où une capture est obligatoire au
#              trait), retrain le NNUE recipe v5 dessus, bench head-
#              to-head vs v5.
#
#              Hypothèse (cf. [9] TalkChess + [5] arXiv 2412.17948 +
#              [8] Stockfish wiki) : un échantillonnage non-filtré
#              attrape des positions tactiques dont le label `score`
#              est trompeur (vrai score = post-rafle, pas celui que
#              l'eval voit). Filtrer ces positions = signal training
#              plus propre = NNUE plus forte sans changer ni l'archi
#              ni le volume.
#
#              Précédent empirique direct [9] : Stockfish nnue-pytorch
#              est passé de -700 ELO à compétitif essentiellement
#              avec cette technique.
#
# expected_duration: ~8-12h sur 4 vCPU CCX23 :
#                    * gen-data 200K @ depth 16 avec quiet filter (~6h)
#                    * train (~1h)
#                    * bench (~1h)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0043-quiet-filter-experiment"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=50000           # 4 × 50K = 200K records. Plus que le pilote
                          # 0025a (100K) pour avoir un signal stat
                          # plus solide ; moins qu'un full 1M parce
                          # qu'on veut un verdict en ~12h max.
EVAL_DEPTH=16             # même que 0025a — variable testée = quiet
                          # filter, pas la depth.
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=20000           # distinct de tous les seeds antérieurs

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$NNUE_FILE" ] && [ -f "$NNUE_FILE" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "shards: $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records @ depth $EVAL_DEPTH"
echo "filter: --quiet-only (skip tactical positions)"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== Phase 0a : gen-data 200K WITH --quiet-only, v5 labeller ==="
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
echo "=== merging into quiet-only-200K.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ, RECORD_SZ = 8, 38
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "quiet-only-200K.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/quiet-only-200K.bin")
PY

DATASET="$ART/quiet-only-200K.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
[ -f "$MASTER" ] || { echo "ABORT: master $MASTER not found"; exit 3; }

echo
echo "=== Phase 0b : train v5-recipe sur dataset quiet-only ==="
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
echo "=== Phase 0c : bench quiet-trained vs v5 ==="
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V5" 6 3  2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0043 QUIET FILTER EXPERIMENT VERDICT"
echo "=========================================================="
echo "  gen wall:        ${WALL_GEN}s ($(python3 -c "print(round($WALL_GEN/3600,1))")h)"
echo "  train wall:      ${TRAIN_SEC}s"
echo "  best arch:       $BEST_ARCH"
echo "  records (quiet): $((NSHARDS * PER_SHARD))"
echo
echo "  vs handcrafted:    rate=$RATE_HC"
echo "  vs v5 (depth 6):   rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):  rate=$RATE_V5_D10"
echo
echo "  References :"
echo "    v5 reference vs handcrafted: 0.852"
echo "    Cycle 9 100K (no quiet filter) vs v5 d10: 0.500 (tie)"
echo
echo "  Decision (per docs/archives/ROADMAP.md Phase 0) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    STRONG GAIN — quiet filter est LA réponse. Généraliser :"
    echo "    régénérer le corpus 1M complet avec --quiet-only, retrain."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.52) }'; then
    echo "    SOLID GAIN — quiet filter aide. Combiner avec Phase 0b"
    echo "    (master volume) pour cumuler les fixes data-side."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.48) }'; then
    echo "    NEUTRAL — pas de gain net du quiet filter seul. Passer à"
    echo "    Phase 0b (master volume) puis Phase 1 (patterns) si"
    echo "    Phase 0b est aussi neutre."
else
    echo "    REGRESSION — inattendu. Debug le filtre ou le sampling."
fi
echo "=========================================================="
