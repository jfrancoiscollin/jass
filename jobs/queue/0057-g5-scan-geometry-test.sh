#!/usr/bin/env bash
# id: 0057-g5-scan-geometry-test
# description: G5 du docs/archives/SCAN_METHODOLOGY_GAP.md (hypothèse H1).
#              Reproduit la self-play loop de G4-diag (0055) MAIS avec
#              la géométrie pattern v3 Scan-inspired : 8 patterns ×
#              12 squares en strips verticaux (vs 16 × 8 blocs 4×4 en
#              v2). Tout le reste identique : base-3, hybrid skeleton +
#              extras + phase split, LBFGS, --lambda 0.0 (pure BCE WDL),
#              10 iter × 20K records depth 4.
#
# Hypothèse : G1→G4-diag ont systématiquement réfuté l'axe méthodologie
# avec la géométrie v2 (blocs 4×4 horizontaux). La géométrie v3
# (verticaux Scan-style) capture des dynamiques différentes (forward
# push, breakthrough threats, opposition de files) que v2 rate
# structurellement. Si v3 sort un signal là où v2 sort 0/54, la racine
# était la géométrie — pas la méthodologie.
#
# Decision gate :
#   rate vs v6 d10 ≥ 0.10 après 10 iter → géométrie ÉTAIT la racine,
#                                         escalader G5-prod (volume +
#                                         géométrie v3 = vrai Scan).
#   rate vs v6 d10 < 0.10               → géométrie pas la racine non
#                                         plus. Diagnostic continue avec
#                                         H3 (bootstrap) ou H2 (volume).
#
# expected_duration: ~3-4h sur 8 vCPU CCX33 :
#                    * 10 iter × (gen ~5 min + train ~15-20 min + bench ~5 min)
#                    * pattern v3 = 4.25M weights vs v2 base-3 = 105K
#                      → training ~10-15× plus lent par iter
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0057-g5-scan-geometry-test"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NUM_ITERS=10
RECS_PER_ITER=20000
SELF_PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=31000

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "iters: $NUM_ITERS, records/iter: $RECS_PER_ITER, depth: $SELF_PLAY_DEPTH"
echo "patterns: v3 (8 × 12 vertical strips, ~4.25M weights base-3)"
echo "v5/v6/v7 refs: $V5 / ${V6:-<missing>} / ${V7:-<missing>}"

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

echo
echo "=== Bootstrap : g5-v0.jpat (v3 geometry, skeleton init) ==="
INIT_JPAT="$ART/g5-v0.jpat"
python3 tools/make_pattern_init.py \
    --out "$INIT_JPAT" \
    --patterns v3 \
    --init-man 100 --init-king 300
ls -lh "$INIT_JPAT"

PREV_JPAT="$INIT_JPAT"
RATES_LOG="$ART/iter-rates.tsv"
echo -e "iter\trate_vs_prev_d6\trate_vs_v6_d10" > "$RATES_LOG"

START=$(date +%s)
for iter in $(seq 1 "$NUM_ITERS"); do
    echo
    echo "============ iter $iter / $NUM_ITERS ============"
    DATA="$ART/iter${iter}-data.bin"
    NEW_JPAT="$ART/g5-v${iter}.jpat"
    seed=$((SEED_BASE + iter * 100))

    echo "-- gen-data $RECS_PER_ITER records via current pattern v3 net --"
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

    echo "-- train pattern v3 hybrid base-3 extras phase-split, pure BCE WDL --"
    python3 tools/train_pattern.py \
        --data           "$DATA" \
        --out            "$NEW_JPAT" \
        --patterns       v3 \
        --hybrid --extras --phase-split \
        --pattern-base   3 \
        --init-man       100 \
        --init-king      300 \
        --optimizer      lbfgs \
        --epochs         20 \
        --lr             1.0 \
        --lambda         0.0 \
        --score-scale    0.01 \
        --weight-decay   1e-5 \
        --lbfgs-max-iter 20 \
        --lbfgs-history  10 \
        --lbfgs-early-stop-patience 4 \
        --symmetry \
        --num-seeds      1 \
        --seed           "$seed" \
        2>&1 | tee "$ART/iter${iter}-train.log" | tail -20

    echo "-- bench new (v3-v$iter) vs previous (v3-v$((iter-1))) at depth 6 --"
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

    echo -e "${iter}\t${RATE_PREV}\t${RATE_V6}" >> "$RATES_LOG"
    echo "  iter $iter : vs prev = $RATE_PREV ; vs v6 d10 = $RATE_V6"
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
echo "       0057 G5-SCAN-GEOMETRY VERDICT"
echo "=========================================================="
echo "  wall:              ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  iters:             $NUM_ITERS × $RECS_PER_ITER records (v3 geometry)"
cat "$RATES_LOG" | column -t
echo
echo "  Final pattern-v3-v${NUM_ITERS} vs :"
echo "    handcrafted:       $R_HC"
echo "    v5 d6  / d10:      $R_V5_D6 / $R_V5_D10"
[ -n "$R_V6_D10" ] && echo "    v6 d10:            $R_V6_D10"
[ -n "$R_V7_D10" ] && echo "    v7 d10:            $R_V7_D10"
echo
echo "  Reference v2 geometry (G4-diag 0055) :"
echo "    iter 10 final vs v6 d10 : 0/54 (FLAT)"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §H1) :"
if [ -n "$R_V6_D10" ] && awk -v r="$R_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    GEOMETRY WAS THE BOTTLENECK — v3 verticaux unlock vs v2 blocs."
    echo "    Suite : G5-prod (volume + géométrie v3 = vrai Scan)."
    echo "    On a une racine identifiée pour la première fois."
elif awk -v r="$R_V5_D10" 'BEGIN { exit !(r >= 0.05) }'; then
    echo "    PROGRÈS NET vs v5 (mais palier vs v6). Géométrie aide mais"
    echo "    pas seule racine. Combiner H3 (bootstrap) ou H2 (volume)."
else
    echo "    FLAT — géométrie n'est pas la racine non plus. Diagnostic"
    echo "    continue : tester H3 (bootstrap depuis v7) puis H2 (scale-up"
    echo "    self-play à 200K records/iter). Pattern axis reste un puzzle."
fi
echo "=========================================================="
