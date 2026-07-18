#!/usr/bin/env bash
# id: 0063-h2-volume-scaleup-kitchen-sink
# description: H2 du docs/archives/SCAN_METHODOLOGY_GAP.md. Scale-up volume self-
#              play : 10 iter × 200K records depth 6 (vs 20K depth 4 en
#              G4-diag/G5-diag). Tout le reste identique : base-3 hybrid
#              + extras + phase split, pure BCE WDL, LBFGS, 1 seed.
#
# Hypothèse : G4-diag (200K total positions) trop bruyant pour
# distinguer good patterns de bad au gradient. Scan/Kingsrow ont
# utilisé millions/milliards de games. Volume × 100 = 2M positions
# pourrait sortir un signal.
#
# Géométrie : v2 par défaut (la seule sur main). À pointer vers v3
# (--patterns v3) si PR #101 mergée et G5 a montré un signal.
#
# Decision gate :
#   rate vs v6 d10 ≥ 0.10 après 10 iter → volume était partiellement
#                                         la racine. G2-prod à
#                                         envisager (scale × 5 encore).
#   < 0.10                              → volume n'est pas suffisant
#                                         seul. Reste H3/H4.
#
# expected_duration: ~1-2 jours wall sur 8 vCPU CCX33 :
#                    * gen-data 200K × 10 iter via pattern self-play
#                      depth 6 (~1.5-2h chaque)
#                    * train pattern (~15-20 min chaque)
#                    * bench (~5 min chaque)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0063-h2-volume-scaleup-kitchen-sink"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NUM_ITERS=10
RECS_PER_ITER=200000
SELF_PLAY_DEPTH=6     # vs 4 en G4-diag — labels plus précis
MAX_PLIES=200
SEED_BASE=32000
PATTERN_SET="v3"      # PR #101 mergée — Scan-aligned geometry

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "iters: $NUM_ITERS × $RECS_PER_ITER records depth $SELF_PLAY_DEPTH"
echo "patterns: $PATTERN_SET"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

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

INIT_JPAT="$ART/h2-v0.jpat"
python3 tools/make_pattern_init.py \
    --out "$INIT_JPAT" \
    --init-man 100 --init-king 300
ls -lh "$INIT_JPAT"

PREV_JPAT="$INIT_JPAT"
RATES_LOG="$ART/iter-rates.tsv"
echo -e "iter\trate_vs_prev_d6\trate_vs_v6_d10\tpearson_vs_v7" > "$RATES_LOG"

START=$(date +%s)
for iter in $(seq 1 "$NUM_ITERS"); do
    echo
    echo "============ iter $iter / $NUM_ITERS ============"
    DATA="$ART/iter${iter}-data.bin"
    NEW_JPAT="$ART/h2-v${iter}.jpat"
    seed=$((SEED_BASE + iter * 100))

    NSHARDS=$(nproc)
    PER_SHARD=$(( (RECS_PER_ITER + NSHARDS - 1) / NSHARDS ))
    pids=()
    for shard in $(seq 1 "$NSHARDS"); do
        s=$((seed + shard))
        (
            ./build/jass --gen-data-wdl "$PER_SHARD" \
                "$ART/iter${iter}-shard${shard}.bin" \
                "$SELF_PLAY_DEPTH" "$SELF_PLAY_DEPTH" "$MAX_PLIES" "$s" \
                --nnue "$PREV_JPAT" \
                > "$ART/iter${iter}-shard${shard}.log" 2>&1
        ) &
        pids+=($!)
    done
    fail=0
    for p in "${pids[@]}"; do wait "$p" || fail=$((fail + 1)); done
    [ "$fail" -eq 0 ] || { echo "ABORT iter $iter : $fail shards failed"; exit 4; }

    python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"; HEADER_SZ = 8
art = Path("$ART")
shards = sorted(art.glob("iter${iter}-shard*.bin"))
total = 0
with (art / "iter${iter}-data.bin").open("wb") as out:
    out.write(MAGIC); out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:]); total += cnt
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/iter${iter}-data.bin")
PY

    python3 tools/train_pattern.py \
        --data           "$DATA" \
        --out            "$NEW_JPAT" \
        --patterns       "$PATTERN_SET" \
        --hybrid --extras --phase-split --mobility \
        --pattern-base   3 \
        --init-man       100 --init-king 300 \
        --optimizer      lbfgs \
        --epochs         20 \
        --lr             1.0 \
        --lambda         0.0 \
        --score-scale    0.01 \
        --weight-decay   1e-5 \
        --lbfgs-max-iter 20 --lbfgs-history 10 \
        --lbfgs-early-stop-patience 4 \
        --symmetry \
        --num-seeds      1 \
        --seed           "$seed" \
        2>&1 | tee "$ART/iter${iter}-train.log" | tail -20

    ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$PREV_JPAT" 6 3 \
        2>&1 | tee "$ART/iter${iter}-bench-vs-prev.log" | tail -2
    RATE_PREV=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-prev.log" | head -1 | awk '{print $3}')

    if [ -n "$V6" ]; then
        ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$V6" 10 3 \
            2>&1 | tee "$ART/iter${iter}-bench-vs-v6.log" | tail -2
        RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-v6.log" | head -1 | awk '{print $3}')
    else
        RATE_V6="-"
    fi

    # H5 — non-binary metric : Pearson correlation pattern vs v7 outputs.
    PEARSON="-"
    if [ -n "$V7" ]; then
        PEARSON=$(python3 tools/pattern_eval_correlation.py \
            --pattern "$NEW_JPAT" --ref "$V7" --data "$DATA" --n 1000 \
            2>"$ART/iter${iter}-pearson.log" \
            | grep -oE 'pearson_r = [-+0-9.]+' | head -1 | awk '{print $3}')
        [ -z "$PEARSON" ] && PEARSON="-"
    fi

    echo -e "${iter}\t${RATE_PREV}\t${RATE_V6}\t${PEARSON}" >> "$RATES_LOG"
    echo "  iter $iter : vs prev=$RATE_PREV ; vs v6 d10=$RATE_V6 ; pearson vs v7=$PEARSON"
    PREV_JPAT="$NEW_JPAT"
done
WALL=$(( $(date +%s) - START ))

echo
echo "=== final bench vs v5/v6/v7 ==="
./build/jass --benchmark-nnue              "$PREV_JPAT"            2>&1 | tee "$ART/final-vs-hc.log" | tail -2
./build/jass --benchmark-nnue-vs-nnue      "$PREV_JPAT" "$V5"  6 3 2>&1 | tee "$ART/final-vs-v5-d6.log"  | tail -2
./build/jass --benchmark-nnue-vs-nnue      "$PREV_JPAT" "$V5" 10 3 2>&1 | tee "$ART/final-vs-v5-d10.log" | tail -2
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$PREV_JPAT" "$V6" 10 3 2>&1 | tee "$ART/final-vs-v6-d10.log" | tail -2
[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$PREV_JPAT" "$V7" 10 3 2>&1 | tee "$ART/final-vs-v7-d10.log" | tail -2

R_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/final-vs-hc.log"     | head -1 | awk '{print $3}')
R_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v5-d6.log"  | head -1 | awk '{print $3}')
R_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v5-d10.log" | head -1 | awk '{print $3}')
R_V6_D10=""; R_V7_D10=""
[ -f "$ART/final-vs-v6-d10.log" ] && R_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v6-d10.log" | head -1 | awk '{print $3}')
[ -f "$ART/final-vs-v7-d10.log" ] && R_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0058 H2 VOLUME SCALEUP VERDICT"
echo "=========================================================="
echo "  wall:              ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  iters:             $NUM_ITERS × $RECS_PER_ITER records (×100 vs G4-diag)"
echo "  patterns:          $PATTERN_SET"
cat "$RATES_LOG" | column -t
echo
echo "  Final pattern-v${NUM_ITERS} vs :"
echo "    handcrafted:       $R_HC"
echo "    v5 d6 / d10:       $R_V5_D6 / $R_V5_D10"
[ -n "$R_V6_D10" ] && echo "    v6 d10:            $R_V6_D10"
[ -n "$R_V7_D10" ] && echo "    v7 d10:            $R_V7_D10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §H2) :"
if [ -n "$R_V6_D10" ] && awk -v r="$R_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    VOLUME WAS A FACTOR — scale-up débloque vs G4-diag à 200K total."
    echo "    Suite : H2-prod (1M+/iter) ou combiner avec H1/H3."
else
    echo "    FLAT même à ×100 volume — volume seul pas la racine."
    echo "    Suite : H3 (bootstrap depuis master) ou H4 (mobility)."
fi
echo "=========================================================="
