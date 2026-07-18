#!/usr/bin/env bash
# id: 0047-d3-pattern-v2-on-quiet-data
# description: Diagnostic D3 (cf. docs/archives/SCAN_ARCHITECTURE_NOTES.md §6).
#              Re-train pattern v2 avec EXACTEMENT la même recipe Phase 1
#              que 0046 — mais sur le dataset quiet-only 200K de 0043
#              (au lieu du depth20-1M sans filtre de 0010).
#
#              Hypothèse testée : le flat-line de 0046 venait du data
#              sale (positions tactiques sans label fiable), pas de
#              l'archi pattern. Si rate vs v5 d10 saute à ≥0.10, data
#              quality était la racine ; si ça reste 0, c'est bien
#              l'archi/le squelette structurel qui manque (passer D2/D1).
#
#              Notes :
#              * Volume divisé par 5 (200K vs 1M) — risque de réduction
#                de signal, mais 0043 a montré que 200K quiet bat 1M
#                sale sur l'archi MLPNetworkQ. Si l'effet existe, il
#                devrait être visible.
#              * Toute la recipe Phase 1 conservée (symmetry, score-scale,
#                multi-seed, cosine LR) pour isoler purement la variable
#                « data quality ».
#
# expected_duration: ~2h sur 4 vCPU CCX23 :
#                    * 3 runs train v2 × ~20 min chacun (~1h, data plus petit)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0047-d3-pattern-v2-on-quiet-data"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0043-quiet-filter-experiment/artefacts.src/quiet-only-200K.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "dataset: $DATASET ($(stat -c %s "$DATASET") bytes)"
echo "v5 ref:  $V5"

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
echo "=== train pattern v2 — D3 (Phase 1 recipe, quiet-only 200K data) ==="
OUT_JPAT="$ART/pattern-v2-d3.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --epochs         30 \
    --batch          4096 \
    --lr             1e-2 \
    --lambda         0.5 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --grad-clip      1.0 \
    --warmup-frac    0.05 \
    --cosine-schedule \
    --symmetry \
    --num-seeds      3 \
    --seed           42 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

ls -lh "$OUT_JPAT"

echo
echo "=== bench vs handcrafted (depth 6) ==="
./build/jass --benchmark-nnue "$OUT_JPAT" 2>&1 | tee "$ART/bench-vs-hc.log"
echo "=== bench vs v5 (depth 6) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
echo "=== bench vs v5 (depth 10) ==="
./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"

RATE_HC=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0047 D3 PATTERN v2 ON QUIET-ONLY DATA VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References :"
echo "    0046 (Phase 1, sale 1M)              : 0/54 vs v5 d6, 0/54 vs v5 d10"
echo "    0025a-7 (no Phase 1, sale 1M)        : 3/54 vs v5 d6, 0/54 vs v5 d10"
echo "    0043 MLPNetworkQ (quiet 200K)        : 0.472 vs v5 d6, 0.639 vs v5 d10"
echo
echo "  Decision (per docs/archives/SCAN_ARCHITECTURE_NOTES.md §D3) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.20) }'; then
    echo "    DATA WAS THE BOTTLENECK — data quality débloque l'archi pattern."
    echo "    Suite : appliquer quiet+pv-extract sur le set d'entraînement"
    echo "    pattern, et probablement Phase 2 self-play sur cette base saine."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRÈS PARTIEL — data quality aide mais pas suffisant."
    echo "    Suite : D2 (base-3 encoding) pour réduire la sparsité."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.0) }'; then
    echo "    SIGNAL MARGINAL — data quality donne quelques victoires"
    echo "    mais le squelette structurel manque. Direct D1 (hybrid)."
else
    echo "    FLAT-LINE confirmé — data n'était PAS la racine."
    echo "    Direct vers D1 (hybrid pattern+material) — c'est probablement"
    echo "    le squelette structurel qui manque, pas la qualité des labels."
fi
echo "=========================================================="
