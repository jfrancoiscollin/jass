#!/usr/bin/env bash
# id: 0049-d2-hybrid-base3-pattern-v2
# description: Diagnostic D2 du docs/archives/SCAN_ARCHITECTURE_NOTES.md. Re-train
#              pattern v2 SUR LE MÊME dataset que 0048 (depth20-1M.bin),
#              avec hybrid skeleton (D1 acquis : 6/54 vs v5 d6) ET
#              encoding base-3 Scan-aligned (kings folded dans patterns,
#              valeur séparément par king_value).
#
# Hypothèse testée : la sparsité (6.25M poids base-5 → ~160 visits/bucket
# sur 1M, beaucoup moins pour buckets king-rare) bridait la convergence.
# En base-3 : 16 × 3^8 = 105K poids (60× plus dense). Chaque bucket
# devrait recevoir ~10K visits sur 1M records → convergence stable.
#
# C'est aussi le design exact de Scan (cf. eval.cpp dans le mirror
# rhalbersma/scan) : base-3 + skeleton material+PST.
#
# Decision gate :
#   rate vs v5 d10 ≥ 0.30 → archi pattern hybrid+base3 viable → Phase 2.
#   ∈ [0.15, 0.30]        → progrès net, considérer scaler dataset (+quiet
#                           via 0043 data, ou 1M complet quiet+pv-extract).
#   ∈ (0.05, 0.15)        → mieux que D1 mais pas suffisant. Décision
#                           difficile : Phase 2 risquée vs abandon.
#   ≤ 0.05                → base-3 ne sauve pas le supervised. Abandon
#                           pattern session, focus axe data (v7 1M).
#
# expected_duration: ~30-45 min sur 4 vCPU CCX23 :
#                    * 3 runs train hybrid base-3 × ~5-7 min (~20 min,
#                      60× moins de poids = beaucoup plus rapide)
#                    * bench (~15 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0049-d2-hybrid-base3-pattern-v2"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
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
echo "=== train pattern v2 HYBRID BASE-3 — D2 (JPAT v3, Scan-aligned) ==="
OUT_JPAT="$ART/pattern-v2-d2-hybrid-base3.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
    --pattern-base   3 \
    --init-man       100 \
    --init-king      300 \
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
echo "       0049 D2 PATTERN v2 HYBRID BASE-3 VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  jpat size:            $(stat -c %s "$OUT_JPAT") bytes"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References (memoires) :"
echo "    0048 D1 hybrid base-5         : 0/18 hc, 6/54 d6, 0/54 d10"
echo "    0046 Phase 1 pure pattern     : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    Smoke 1-epoch hybrid base-3   : 4/18 vs hc (preuve format)"
echo "    Scan archi reference          : base-3 + hybrid + années tuning"
echo
echo "  Decision (per docs/archives/SCAN_ARCHITECTURE_NOTES.md §D2) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.30) }'; then
    echo "    ARCHI VIABLE — base-3 + hybrid Scan-aligned débloque."
    echo "    Suite : Phase 2 self-play, ou scaler dataset (quiet+pv-extract"
    echo "    sur cette base saine)."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.15) }'; then
    echo "    PROGRÈS NET — base-3 + hybrid avance vs D1 seul (0/54 d10)."
    echo "    Suite : scaler le dataset (quiet+pv-extract via 0045 data)"
    echo "    avant Phase 2."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.05) }'; then
    echo "    PROGRÈS MARGINAL — meilleur que D1 mais loin du gate Phase 2."
    echo "    Décision difficile : Phase 2 €20-40 risquée vs abandon."
else
    echo "    FLAT — base-3 ne sauve pas le supervised. Honnête conclusion :"
    echo "    le supervised cheap ne mène pas notre archi pattern à un niveau"
    echo "    compétitif. Abandon pattern session, focus axe data (v7)."
fi
echo "=========================================================="
