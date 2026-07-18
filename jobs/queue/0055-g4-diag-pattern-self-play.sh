#!/usr/bin/env bash
# id: 0055-g4-diag-pattern-self-play
# description: G4-diag du docs/archives/SCAN_METHODOLOGY_GAP.md (post-révision
#              coût). Self-play TD-leaf style pour pattern v2 hybrid
#              base-3 + extras + phase split. 10 itérations, 20K
#              records par iter (low-volume diagnostic).
#
# Hypothèse testée : G1-G3b (supervised cheap) tous flat. La seule
# variante méthodologique non-testée est self-play : labels WDL
# générés par le réseau lui-même contre lui-même, pas par un évaluateur
# externe. C'est exactement ce que Scan/Kingsrow font selon la note
# Letouzey + crédit Gilbert. Si ça aussi est flat, on a une preuve
# diagnostic complète que pattern v2 supervised/self-play à 10 iter
# n'est pas le bon levier.
#
# Loss : --lambda 0.0 (pure BCE WDL, sans score MSE). Scan-aligned.
# Optimizer : LBFGS (G1 a montré convergence stable même si trivial
# minimum). 1 seed par iter (pas de seed averaging, on itère à la place).
#
# Bootstrap : tools/make_pattern_init.py génère pattern-v0.jpat avec
# skeleton man=100 king=300 EG=MG, patterns=0. Premier auto-jeu joue
# essentiellement du material counting → WDL informatif pour le premier
# train.
#
# Decision gate (post-révision §G4-diag) :
#   rate vs v6 d10 ≥ 0.20 après 10 iter → self-play unlock, G4-prod ;
#   < 0.20                              → diagnostic chain G1→G4-diag
#                                         complète, abandon pattern axis
#                                         FERME pour cette ère du projet.
#
# expected_duration: ~6-8h sur 4 vCPU CCX23 (~3-4h sur 8 vCPU CCX33) :
#                    * 10 iter × (gen ~5 min + train ~30 min + bench ~5 min)
#                    * final bench vs v5/v6/v7 (~5 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0055-g4-diag-pattern-self-play"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

NUM_ITERS=10
RECS_PER_ITER=20000
SELF_PLAY_DEPTH=4   # both eval_depth and play_depth in gen-data-wdl
MAX_PLIES=200
SEED_BASE=30000

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "iters: $NUM_ITERS, records/iter: $RECS_PER_ITER, depth: $SELF_PLAY_DEPTH"
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
echo "=== Bootstrap : pattern-v0.jpat (skeleton init man=100 king=300) ==="
INIT_JPAT="$ART/pattern-v0.jpat"
python3 tools/make_pattern_init.py --out "$INIT_JPAT" --init-man 100 --init-king 300
ls -lh "$INIT_JPAT"

PREV_JPAT="$INIT_JPAT"

# Per-iter logs : rate (new vs prev) at depth 6, rate vs v6 d10.
RATES_LOG="$ART/iter-rates.tsv"
echo -e "iter\trate_vs_prev_d6\trate_vs_v6_d10" > "$RATES_LOG"

START=$(date +%s)
for iter in $(seq 1 "$NUM_ITERS"); do
    echo
    echo "============ iter $iter / $NUM_ITERS ============"
    DATA="$ART/iter${iter}-data.bin"
    NEW_JPAT="$ART/pattern-v${iter}.jpat"
    seed=$((SEED_BASE + iter * 100))

    echo "-- gen-data $RECS_PER_ITER records via current pattern net --"
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

    # Merge shards
    python3 - <<PY
import struct
from pathlib import Path
MAGIC = b"JNNW"
HEADER_SZ = 8
art = Path("$ART")
shards = sorted(art.glob("iter${iter}-shard*.bin"))
total = 0
with (art / "iter${iter}-data.bin").open("wb") as out:
    out.write(MAGIC); out.write(struct.pack("<I", 0))
    for s in shards:
        raw = s.read_bytes()
        cnt = struct.unpack_from("<I", raw, 4)[0]
        out.write(raw[HEADER_SZ:])
        total += cnt
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} records into {art}/iter${iter}-data.bin")
PY

    echo "-- train pattern v2 hybrid base-3 extras phase-split, pure BCE WDL --"
    python3 tools/train_pattern.py \
        --data           "$DATA" \
        --out            "$NEW_JPAT" \
        --patterns       v2 \
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

    echo "-- bench new pattern (v$iter) vs previous (v$((iter-1))) at depth 6 --"
    ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$PREV_JPAT" 6 3 \
        2>&1 | tee "$ART/iter${iter}-bench-vs-prev.log" | tail -2
    RATE_PREV=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-prev.log" | head -1 | awk '{print $3}')

    if [ -n "$V6" ]; then
        echo "-- bench new pattern (v$iter) vs v6 at depth 10 --"
        ./build/jass --benchmark-nnue-vs-nnue "$NEW_JPAT" "$V6" 10 3 \
            2>&1 | tee "$ART/iter${iter}-bench-vs-v6.log" | tail -2
        RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/iter${iter}-bench-vs-v6.log" | head -1 | awk '{print $3}')
    else
        RATE_V6="-"
    fi

    echo -e "${iter}\t${RATE_PREV}\t${RATE_V6}" >> "$RATES_LOG"
    echo "  iter $iter : vs prev = $RATE_PREV ; vs v6 d10 = $RATE_V6"

    # Always-accept policy for diag : the new pattern becomes the base
    # for next iter regardless of vs-prev rate. Variance noise at low
    # volume isn't a reliable winner-keeper signal anyway.
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
echo "       0055 G4-DIAG PATTERN SELF-PLAY VERDICT"
echo "=========================================================="
echo "  wall:              ${WALL}s ($(python3 -c "print(round($WALL/3600,1))")h)"
echo "  iters complete:    $NUM_ITERS × $RECS_PER_ITER records each"
echo "  per-iter rates :   (see $RATES_LOG)"
cat "$RATES_LOG" | column -t
echo
echo "  Final pattern-v${NUM_ITERS} vs :"
echo "    handcrafted:       $R_HC"
echo "    v5 d6  / d10:      $R_V5_D6 / $R_V5_D10"
[ -n "$R_V6_D10" ] && echo "    v6 d10:            $R_V6_D10"
[ -n "$R_V7_D10" ] && echo "    v7 d10:            $R_V7_D10"
echo
echo "  Diagnostic chain G1→G3b history :"
echo "    G1 LBFGS              : 0/54 vs v5 d10"
echo "    G2 distill v7         : 0/54 vs v5 d10"
echo "    G3a king PST+balance  : 0/54 vs v5 d10"
echo "    G3b phase split skel  : 0/54 vs v5 d10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §G4-diag) :"
if [ -n "$R_V6_D10" ] && awk -v r="$R_V6_D10" 'BEGIN { exit !(r >= 0.20) }'; then
    echo "    SELF-PLAY UNLOCK — méthodo Scan-aligned débloque. Suite :"
    echo "    G4-prod (~€10-20, ~1 semaine) avec 100K-300K games/iter,"
    echo "    20 iter, depth 6."
elif awk -v r="$R_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRÈS NET vs v5 — pas franchi le gate G4-prod mais signal."
    echo "    Décision difficile : G4-prod risquée vs accepter le palier."
else
    echo "    FLAT — diagnostic chain COMPLÈTE G1→G3b→G4-diag."
    echo "    ABANDON FERME pattern axis pour cette ère du projet."
    echo "    Conclusion empirique : 5 hypothèses (optimizer / label /"
    echo "    features / phase / méthodo self-play) systématiquement"
    echo "    réfutées avec ~€10 total. Pattern axis nécessite un"
    echo "    leverage qualitatif nouveau (idée fraîche ou réplication"
    echo "    Scan complète) pour être relancée. Focus axe data v8."
fi
echo "=========================================================="
