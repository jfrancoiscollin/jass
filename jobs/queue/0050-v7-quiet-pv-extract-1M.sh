#!/usr/bin/env bash
# id: 0050-v7-quiet-pv-extract-1M
# description: v7 production run. Extrapolation directe de 0045 (v6
#              500K) à 1M complet avec la même recipe quiet+pv-extract.
#              ROI le plus clair restant sur l'axe data (pattern axis
#              gelé après 0049, cf. docs/archives/SCAN_METHODOLOGY_GAP.md).
#
#              v6 (0045 500K) faisait +39 ELO vs v5 d10. Extrapolation
#              naïve à 1M : +50-80 ELO vs v5 d10 si le gain est linéaire
#              en log(volume) (typique des courbes d'apprentissage).
#              Coût mesuré 0045 = 18h gen pour 500K → projection 1M ≈ 36h.
#
# expected_duration: ~40-50h sur 4 vCPU CCX23 :
#                    * gen-data 1M @ depth 16 quiet+pv-extract (~36h)
#                    * train (~2h, 1M records 4 archs)
#                    * bench vs v5 ET vs v6 (~1h)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0050-v7-quiet-pv-extract-1M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NSHARDS=4
PER_SHARD=250000          # 4 × 250K = 1M records (2× v6).
EVAL_DEPTH=16             # identique 0043/0045 (variable testée = volume).
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=22000           # distinct des seeds 0043 (20001-4) et 0045 (21001-4).
PV_EXTRACT=3              # validé en 0045.

NNUE_FILE=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$NNUE_FILE" ] && [ -f "$NNUE_FILE" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V6" ] && [ -f "$V6" ] || { echo "WARN: v6 NNUE not found, bench vs v6 will be skipped"; V6=""; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "shards: $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records @ depth $EVAL_DEPTH"
echo "filters: --quiet-only --pv-extract $PV_EXTRACT"
echo "v5 labeller: $NNUE_FILE"
echo "v6 bench ref: ${V6:-<not found, skipped>}"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== Phase 0a : gen-data 1M WITH --quiet-only --pv-extract $PV_EXTRACT (v5 labeller) ==="
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
echo "=== merging into v7-quiet-pv-1M.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ, RECORD_SZ = 8, 38
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "v7-quiet-pv-1M.bin").open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/v7-quiet-pv-1M.bin")
PY

DATASET="$ART/v7-quiet-pv-1M.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
[ -f "$MASTER" ] || { echo "ABORT: master $MASTER not found"; exit 3; }

echo
echo "=== Phase 0b : train v6-recipe sur dataset v7 (1M quiet+pv-extract) ==="
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
echo "=== Phase 0c : bench v7 vs handcrafted + vs v5 + vs v6 ==="
./build/jass --benchmark-nnue "$QUANT_OUT" 2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$NNUE_FILE" 6  3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$NNUE_FILE" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"

if [ -n "$V6" ]; then
    ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V6" 6  3 2>&1 | tee "$ART/bench-vs-v6-d6.log"
    ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
fi

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D6=""
RATE_V6_D10=""
if [ -n "$V6" ]; then
    RATE_V6_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d6.log"  | head -1 | awk '{print $3}')
    RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
fi

echo
echo "=========================================================="
echo "       0050 v7 QUIET+PV-EXTRACT 1M VERDICT"
echo "=========================================================="
echo "  gen wall:        ${WALL_GEN}s ($(python3 -c "print(round($WALL_GEN/3600,1))")h)"
echo "  train wall:      ${TRAIN_SEC}s"
echo "  best arch:       $BEST_ARCH"
echo "  records:         $((NSHARDS * PER_SHARD)) (quiet + pv-extract $PV_EXTRACT)"
echo
echo "  vs handcrafted:        rate=$RATE_HC"
echo "  vs v5 (depth 6):       rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):      rate=$RATE_V5_D10"
if [ -n "$V6" ]; then
echo "  vs v6 (depth 6):       rate=$RATE_V6_D6"
echo "  vs v6 (depth 10):      rate=$RATE_V6_D10"
fi
echo
echo "  References :"
echo "    v6 (0045 500K) vs handcrafted: 0.861"
echo "    v6 vs v5 d10:                  0.556 (+39 ELO)"
echo "    v6 vs v5 d6:                   0.722 (+165 ELO)"
echo
echo "  Decision :"
if [ -n "$V6" ] && awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    v7 BEATS v6 — ship v7 as new reference. Continue volume axis"
    echo "    (envisager 2M, master refresh, FMJD scrape)."
elif [ -n "$V6" ] && awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    v7 ≈ v6 — courbe d'apprentissage plate au-delà de 500K."
    echo "    Volume axis exhausted. Pivot vers master refresh / FMJD"
    echo "    pour ajouter du SIGNAL plutôt que du VOLUME."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.55) }'; then
    echo "    v7 ≥ v5 strong (sans v6 ref disponible). Ship v7."
else
    echo "    v7 ≤ v5 ou ≤ v6 — surprise. Investigate : possibilités"
    echo "    overfit sur master, train recipe à revoir, ou variance bench."
fi
echo "=========================================================="
