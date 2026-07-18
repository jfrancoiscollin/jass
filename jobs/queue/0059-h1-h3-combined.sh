#!/usr/bin/env bash
# id: 0059-h1-h3-combined-bootstrap-v3-geometry
# description: H1+H3 combiné. Aligne la self-play loop sur les DEUX
#              hypothèses pattern non-encore-réfutées combinées :
#                * H1 = géométrie v3 verticaux Scan-style (8 × 12 squares)
#                * H3 = bootstrap depuis master games avant self-play
#
# Rationale : 6 hypothèses pattern flat après diag chain G1→G3b+G4-diag
# (méthodologie) + G5/H1 seul (géométrie). Si H1+H3 combiné aussi flat,
# preuve diagnostic très solide qu'aucune variante cheap dans notre
# infra n'unlock l'archi pattern.
#
# Self-play depuis pattern weights=0 produit des games très bruitées
# dans les premières iters (le réseau v0 joue essentiellement random
# au-delà du material counting). Bootstrap = train supervised sur 0014
# master-1600.jnnw (4.7M positions WDL réelles) avec LBFGS pure BCE.
# Produit pattern-bootstrap.jpat avec weights non-triviaux tirés du
# signal master. Puis self-play loop depuis ce starter.
#
# Géométrie v3 (PR #101) = vertical strips 8 patterns × 12 squares.
#
# Decision gate :
#   rate vs v6 d10 ≥ 0.10 après 10 iter → COMBO unlock pattern axis
#   ∈ (0, 0.10)                          → signal marginal mais existe
#   = 0                                  → 7 hypothèses flat. Diagnostic
#                                          combinaisons cheap exhaustif.
#                                          Pattern axis nécessite leverage
#                                          qualitatif nouveau ou abandon.
#
# expected_duration: ~5-7h sur 8 vCPU CCX33 :
#                    * bootstrap supervised sur 4.7M master records v3
#                      geometry (~1-2h, plus lent que v2 car 4.25M poids)
#                    * 10 iter × (gen + train + bench) ~30 min each
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0059-h1-h3-combined"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NUM_ITERS=10
RECS_PER_ITER=20000
SELF_PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=33000
PATTERN_SET="v3"     # H1+H3 combined : v3 verticaux Scan-style + bootstrap

MASTER="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
[ -f "$MASTER" ] || { echo "ABORT: master $MASTER not found"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "master corpus: $MASTER ($(stat -c %s "$MASTER") bytes)"
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

echo
echo "=== Phase H3a : bootstrap supervised sur master games (BCE WDL only) ==="
BOOTSTRAP_JPAT="$ART/pattern-bootstrap.jpat"
START_BOOT=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$MASTER" \
    --out            "$BOOTSTRAP_JPAT" \
    --patterns       "$PATTERN_SET" \
    --hybrid --extras --phase-split \
    --pattern-base   3 \
    --init-man       100 --init-king 300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         0.0 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --lbfgs-max-iter 20 --lbfgs-history 10 \
    --lbfgs-early-stop-patience 5 \
    --symmetry \
    --num-seeds      3 \
    --seed           42 \
    2>&1 | tee "$ART/bootstrap-train.log"
BOOT_SEC=$(( $(date +%s) - START_BOOT ))
ls -lh "$BOOTSTRAP_JPAT"
echo "bootstrap wall: ${BOOT_SEC}s"

echo
echo "=== Bench bootstrap vs handcrafted / v6 (sanity check) ==="
./build/jass --benchmark-nnue              "$BOOTSTRAP_JPAT"            2>&1 | tee "$ART/bootstrap-vs-hc.log" | tail -2
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$BOOTSTRAP_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bootstrap-vs-v6.log" | tail -2
BOOT_HC=$(grep -oE 'score rate: [0-9.]+' "$ART/bootstrap-vs-hc.log" | head -1 | awk '{print $3}')

PREV_JPAT="$BOOTSTRAP_JPAT"
RATES_LOG="$ART/iter-rates.tsv"
echo -e "iter\trate_vs_prev_d6\trate_vs_v6_d10\tpearson_vs_v7" > "$RATES_LOG"

echo
echo "=== Phase H3b : self-play loop depuis bootstrap ==="
START=$(date +%s)
for iter in $(seq 1 "$NUM_ITERS"); do
    echo
    echo "============ iter $iter / $NUM_ITERS ============"
    DATA="$ART/iter${iter}-data.bin"
    NEW_JPAT="$ART/h3-v${iter}.jpat"
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
        --hybrid --extras --phase-split \
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
echo "       0059 H1+H3 COMBINED (v3 geometry + bootstrap) VERDICT"
echo "=========================================================="
echo "  bootstrap wall:    ${BOOT_SEC}s"
echo "  bootstrap vs hc:   $BOOT_HC"
echo "  self-play wall:    ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  patterns:          $PATTERN_SET"
cat "$RATES_LOG" | column -t
echo
echo "  Final pattern-v${NUM_ITERS} vs :"
echo "    handcrafted:       $R_HC"
echo "    v5 d6 / d10:       $R_V5_D6 / $R_V5_D10"
[ -n "$R_V6_D10" ] && echo "    v6 d10:            $R_V6_D10"
[ -n "$R_V7_D10" ] && echo "    v7 d10:            $R_V7_D10"
echo
echo "  Decision (H1+H3 combined, per docs/archives/SCAN_METHODOLOGY_GAP.md) :"
if [ -n "$R_V6_D10" ] && awk -v r="$R_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    COMBO UNLOCK — H1 (géométrie v3) + H3 (bootstrap master) ensemble"
    echo "    débloquent l'archi pattern. Isoler ensuite : H3 seul vs H1 seul"
    echo "    pour identifier la composante critique. Puis scale-up (H2 volume)."
else
    echo "    FLAT — 7 hypothèses pattern systématiquement réfutées avec ~€13"
    echo "    total. Combinaison la plus prometteuse (H1+H3) aussi flat."
    echo "    Conclusion empirique : aucune variante cheap dans notre infra"
    echo "    actuelle n'unlock l'archi pattern. Reste H2 volume (~€10) ou"
    echo "    H4 mobility features (~€3 + 1j dev C++) ou leverage nouveau."
fi
echo "=========================================================="
