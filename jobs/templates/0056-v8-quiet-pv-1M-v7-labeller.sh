#!/usr/bin/env bash
# id: 0056-v8-quiet-pv-1M-v7-labeller
# description: v8 production candidate. Standby — à activer (move
#              templates/→queue/) après verdict G4-diag (0055) OU si on
#              décide d'enchaîner sur l'axe data quand on a un créneau
#              compute.
#
#              Même recipe que v7 (1M records, quiet+pv-extract,
#              recipe v5 master-BCE) MAIS le labelleur est **v7 lui-
#              même** au lieu de v5. C'est le knowledge-bootstrap : on
#              utilise notre meilleur réseau actuel pour produire des
#              labels score plus précis sur les positions self-play,
#              ce qui devrait donner un v8 marginalement plus fort.
#
#              Hypothèse : v7 vs v5 d10 = 0.583 (+58 ELO). Si v7 sait
#              mieux évaluer la profondeur 16 qu'un dataset labellé via
#              v7 capture un signal +20-50 ELO additionnel vs v7 lui-
#              même. C'est l'extrapolation Cycle 8/9/10 (chaque cycle
#              labellé par le précédent gagne).
#
# expected_duration: sur CCX33 (8 vCPU, 32 GB) :
#                    * gen-data 1M quiet+pv-extract depth 16 v7 labeller (~18h, 8 shards)
#                    * train v5 recipe (~2h)
#                    * bench vs v5/v6/v7 (~1h)
#                    Total ~21-24h wall.
#                    (Sur CCX23 ce serait ~38-42h.)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

# Auto-scale on available cores (4 on CCX23 → 4 shards, 8 on CCX33 → 8 shards).
NSHARDS=$(nproc)
RECORDS_TOTAL=1000000
PER_SHARD=$(( (RECORDS_TOTAL + NSHARDS - 1) / NSHARDS ))
EVAL_DEPTH=16             # identique v6/v7 (variable testée = labeller, pas depth).
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=23000           # distinct des seeds antérieurs (v6=21K, v7=22K).
PV_EXTRACT=3              # validé en 0045/0050.

# LABELLER = v7 (knowledge bootstrap, vs v5/v6 dans les runs précédents).
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V7" ] && [ -f "$V7" ] || { echo "ABORT: v7 NNUE not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found (bench ref)"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "shards: $NSHARDS × $PER_SHARD = $((NSHARDS * PER_SHARD)) records @ depth $EVAL_DEPTH"
echo "labeller (v7): $V7"
echo "bench refs : v5=$V5 ; v6=${V6:-<missing>}"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== Phase 0a : gen-data 1M WITH --quiet-only --pv-extract $PV_EXTRACT (v7 labeller) ==="
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
            --nnue "$V7" \
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
echo "=== merging into v8-quiet-pv-1M.bin ==="
python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ = 8
art = Path("$ART")
shards = sorted(art.glob("shard-*.bin"))
total = 0
with (art / "v8-quiet-pv-1M.bin").open("wb") as out:
    out.write(MAGIC); out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/v8-quiet-pv-1M.bin")
PY

DATASET="$ART/v8-quiet-pv-1M.bin"
MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
[ -f "$MASTER" ] || { echo "ABORT: master $MASTER not found"; exit 3; }

echo
echo "=== Phase 0b : train v5-recipe sur dataset v8 (1M quiet+pv-extract via v7 labeller) ==="
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
echo "=== Phase 0c : bench v8 vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$QUANT_OUT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$QUANT_OUT" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$QUANT_OUT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
./build/jass --benchmark-nnue-vs-nnue      "$QUANT_OUT" "$V7"  6 3 2>&1 | tee "$ART/bench-vs-v7-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$QUANT_OUT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
RATE_V7_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d6.log"  | head -1 | awk '{print $3}')
RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0056 v8 QUIET+PV-EXTRACT 1M v7-LABELLER VERDICT"
echo "=========================================================="
echo "  gen wall:           ${WALL_GEN}s ($(python3 -c "print(round($WALL_GEN/3600,1))")h)"
echo "  train wall:         ${TRAIN_SEC}s"
echo "  best arch:          $BEST_ARCH"
echo "  records (quiet+pv): $((NSHARDS * PER_SHARD))"
echo "  labeller:           v7 (knowledge bootstrap)"
echo
echo "  vs handcrafted:     $RATE_HC"
echo "  vs v5 (d6 / d10):   $RATE_V5_D6 / $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 (d10):        $RATE_V6_D10"
echo "  vs v7 (d6 / d10):   $RATE_V7_D6 / $RATE_V7_D10"
echo
echo "  Reference :"
echo "    v7 (0050 1M v5-labeller) vs handcrafted: 0.944"
echo "    v7 vs v5 d10:                            0.583"
echo "    v7 vs v6 d10:                            0.667"
echo
echo "  Decision :"
if awk -v r="$RATE_V7_D10" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    v8 BEATS v7 — knowledge bootstrap a payé. Ship v8 comme"
    echo "    nouvelle référence. Considérer v9 = 1M avec v8 comme labeller."
elif awk -v r="$RATE_V7_D10" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    v8 ≈ v7 — courbe plate au-delà de v7. Knowledge bootstrap"
    echo "    exhaustée à ce volume ; envisager scale-up à 2M ou Phase 0b"
    echo "    (master refresh + FMJD scrape) pour amener de la diversité."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.55) }'; then
    echo "    v8 > v5 mais ≤ v7 — léger drop d'overfitting sur v7's quirks."
    echo "    Ship n'est pas justifié, garder v7 comme référence."
else
    echo "    REGRESSION inattendue. Investigate."
fi
echo "=========================================================="
