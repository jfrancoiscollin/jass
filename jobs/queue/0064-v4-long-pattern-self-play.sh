#!/usr/bin/env bash
# id: 0064-v4-long-pattern-self-play
# description: Test long-patterns hypothesis : v4 = 8 patterns × 14
#              squares (vs v3 = 12 squares). Tout le reste identique au
#              0062 kitchen sink (hybrid + extras + phase split +
#              mobility). Tests si la longueur 14 capture des motifs
#              que v3 ratait.
#
# Hypothèse : nos 10 hypothèses pattern flat ont toutes utilisé des
# patterns ≤ 12 squares. v4 = 14 squares = ~38M weights base-3 (~150
# MB JPAT). Plus de capacité par pattern + 1-2 rangs supplémentaires
# de contexte vertical = peut-être enough pour franchir le seuil de
# calibration.
#
# Self-play loop standard : 10 iter × 20K records depth 4, pure BCE WDL,
# LBFGS. Bootstrap depuis make_pattern_init (skeleton-only, mobility
# weights apprises pendant self-play).
#
# Risque mémoire : LBFGS history (10) × 38M params × 4 bytes = 1.5 GB
# pour les hessian approx. Fit in 32 GB CCX33 mais surveiller OOM.
# Backoff : lbfgs-history réduit à 5 → 760 MB.
#
# Decision gate :
#   rate vs v6 d10 ≥ 0.10 → long patterns helped, scale-up
#   < 0.10                → 11 hypothèses cheap flat
#
# expected_duration: ~5-8h sur 8 vCPU CCX33 :
#                    * train v4 ~5-10× plus lent que v3 (38M vs 4M params)
#                    * 10 iter × (gen ~5-10 min + train ~30-50 min + bench ~5 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0064-v4-long-pattern-self-play"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NUM_ITERS=10
RECS_PER_ITER=20000
SELF_PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=35000
PATTERN_SET="v4"

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "patterns: $PATTERN_SET (8 × 14 squares = ~38M weights base-3)"

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

INIT_JPAT="$ART/v4-v0.jpat"
python3 tools/make_pattern_init.py \
    --out "$INIT_JPAT" --patterns "$PATTERN_SET" \
    --init-man 100 --init-king 300
ls -lh "$INIT_JPAT"

PREV_JPAT="$INIT_JPAT"
RATES_LOG="$ART/iter-rates.tsv"
echo -e "iter\trate_vs_prev_d6\trate_vs_v6_d10\tpearson_vs_v7" > "$RATES_LOG"

START=$(date +%s)
for iter in $(seq 1 "$NUM_ITERS"); do
    echo "============ iter $iter / $NUM_ITERS ============"
    DATA="$ART/iter${iter}-data.bin"
    NEW_JPAT="$ART/v4-v${iter}.jpat"
    seed=$((SEED_BASE + iter * 100))

    NSHARDS=$(nproc)
    PER_SHARD=$(( (RECS_PER_ITER + NSHARDS - 1) / NSHARDS ))
    pids=()
    for shard in $(seq 1 "$NSHARDS"); do
        s=$((seed + shard))
        (./build/jass --gen-data-wdl "$PER_SHARD" \
            "$ART/iter${iter}-shard${shard}.bin" \
            "$SELF_PLAY_DEPTH" "$SELF_PLAY_DEPTH" "$MAX_PLIES" "$s" \
            --nnue "$PREV_JPAT" \
            > "$ART/iter${iter}-shard${shard}.log" 2>&1) &
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
PY

    # LBFGS history reduced to 5 to keep memory < 1 GB for 38M params.
    python3 tools/train_pattern.py \
        --data "$DATA" --out "$NEW_JPAT" \
        --patterns "$PATTERN_SET" \
        --hybrid --extras --phase-split --mobility \
        --pattern-base 3 \
        --init-man 100 --init-king 300 \
        --optimizer lbfgs --epochs 15 --lr 1.0 \
        --lambda 0.0 --score-scale 0.01 --weight-decay 1e-5 \
        --lbfgs-max-iter 15 --lbfgs-history 5 \
        --lbfgs-early-stop-patience 3 \
        --symmetry --num-seeds 1 --seed "$seed" \
        2>&1 | tee "$ART/iter${iter}-train.log" | tail -20

    ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$PREV_JPAT" 6 3 \
        2>&1 | tee "$ART/iter${iter}-bench-vs-prev.log" | tail -2
    RATE_PREV=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-prev.log" | head -1 | awk '{print $3}')
    RATE_V6="-"; PEARSON="-"
    if [ -n "$V6" ]; then
        ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$V6" 10 3 \
            2>&1 | tee "$ART/iter${iter}-bench-vs-v6.log" | tail -2
        RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-v6.log" | head -1 | awk '{print $3}')
    fi
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

echo "=== final bench vs v5/v6/v7 ==="
./build/jass --benchmark-nnue              "$PREV_JPAT"            2>&1 | tee "$ART/final-vs-hc.log" | tail -2
./build/jass --benchmark-nnue-vs-nnue      "$PREV_JPAT" "$V5" 10 3 2>&1 | tee "$ART/final-vs-v5-d10.log" | tail -2
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$PREV_JPAT" "$V6" 10 3 2>&1 | tee "$ART/final-vs-v6-d10.log" | tail -2
[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$PREV_JPAT" "$V7" 10 3 2>&1 | tee "$ART/final-vs-v7-d10.log" | tail -2

R_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/final-vs-hc.log"     | head -1 | awk '{print $3}')
R_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v5-d10.log" | head -1 | awk '{print $3}')
R_V6_D10=""; R_V7_D10=""
[ -f "$ART/final-vs-v6-d10.log" ] && R_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v6-d10.log" | head -1 | awk '{print $3}')
[ -f "$ART/final-vs-v7-d10.log" ] && R_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/final-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0064 V4 LONG PATTERN VERDICT"
echo "=========================================================="
echo "  wall:              ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  patterns:          $PATTERN_SET (14 squares × 8 patterns ~38M weights)"
cat "$RATES_LOG" | column -t
echo
echo "  Final pattern-v10 vs : hc=$R_HC ; v5 d10=$R_V5_D10 ; v6 d10=$R_V6_D10 ; v7 d10=$R_V7_D10"
echo
if [ -n "$R_V6_D10" ] && awk -v r="$R_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    LONG PATTERNS UNLOCK — v4 14-square débloque vs v3 12-square."
    echo "    Suite : scale-up volume + même geometry."
else
    echo "    FLAT — 11 hypothèses cheap toutes réfutées. Long patterns"
    echo "    n'ont pas aidé non plus."
fi
echo "=========================================================="
