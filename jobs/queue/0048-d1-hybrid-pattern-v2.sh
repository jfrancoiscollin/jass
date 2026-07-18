#!/usr/bin/env bash
# id: 0048-d1-hybrid-pattern-v2
# description: Diagnostic D1 du PATTERN_ROADMAP / docs/archives/SCAN_ARCHITECTURE_NOTES.md.
#              Re-train pattern v2 SUR LE MÊME dataset (depth20-1M.bin
#              de 0010, identique 0046/0025a-7), MAIS avec le squelette
#              structurel hybrid : pattern eval = bias + man_value *
#              (Wmen - Bmen) + king_value * (Wkings - Bkings) +
#              sum_patterns. man_value et king_value sont des paramètres
#              trainables initialisés à ~100/300 cp.
#
# Hypothèse testée : le flat-line de 0046/0047 venait du manque de
# squelette structurel. Les patterns ne pouvaient pas apprendre la
# valeur absolue des pièces depuis le seul signal score MSE — d'où
# l'optimum trivial pred=0. Avec material/king comme features
# additives initialisées sensiblement, les patterns n'ont plus qu'à
# apprendre la correction positionnelle résiduelle.
#
# Précédent empirique direct (smoke test 5K records, 2 epochs) :
# pattern pur (PR #86) → 0/18 vs handcrafted ; pattern hybrid (cette
# PR, init man=100/king=300) → 4/18 vs handcrafted en 2 epochs. Signal
# clair que le squelette débloque l'archi.
#
# Decision gate :
#   rate vs v5 d10 ≥ 0.30 → archi pattern hybrid viable → Phase 2 self-play.
#   rate vs v5 d10 ∈ [0.10, 0.30] → progrès net, considérer D2 (base-3) ou
#                                   master volume sur cette base avant Phase 2.
#   rate vs v5 d10 < 0.10 → squelette ne suffit pas. Soit Phase 2 quand même
#                          (la self-play génère des distributions différentes),
#                          soit abandon pattern session.
#
# expected_duration: ~3-4h sur 4 vCPU CCX23 :
#                    * 3 runs train hybrid v2 × ~45 min (~2.5h)
#                    * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0048-d1-hybrid-pattern-v2"
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
echo "=== train pattern v2 HYBRID — D1 (JPAT v2, material+king skeleton) ==="
OUT_JPAT="$ART/pattern-v2-d1-hybrid.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
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
echo "       0048 D1 PATTERN v2 HYBRID VERDICT"
echo "=========================================================="
echo "  train wall:           ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:       rate=$RATE_HC"
echo "  vs v5 (depth 6):      rate=$RATE_V5_D6"
echo "  vs v5 (depth 10):     rate=$RATE_V5_D10"
echo
echo "  References :"
echo "    0046 (Phase 1 pure pattern, sale 1M)  : 0/18 vs hc, 0/54 vs v5 d10"
echo "    0047 (Phase 1 pure pattern, quiet)    : 0/18 vs hc, 0/54 vs v5 d10"
echo "    0025a-7 (pure WDL pattern v2)         : 0/18 vs hc, 0/54 vs v5 d10, 3/54 d6"
echo "    Smoke 2-epoch 5K hybrid               : 4/18 vs hc (preuve concept)"
echo
echo "  Decision (per docs/archives/SCAN_ARCHITECTURE_NOTES.md §D1) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.30) }'; then
    echo "    ARCHI HYBRID VIABLE — squelette structurel débloque les patterns."
    echo "    Suite : Phase 2 (self-play loop pattern hybrid), ou D2 (base-3)"
    echo "    pour pousser encore. Le squelette structurel était la clé."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRÈS NET — hybrid aide vs flat-line des Phase 1 runs."
    echo "    Suite : D2 (base-3 encoding) pour réduire la sparsité, ou"
    echo "    master volume pour densifier les visits/bucket."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r > 0.0) }'; then
    echo "    SIGNAL FAIBLE — hybrid bouge quelque chose mais marginal."
    echo "    Le supervised seul ne suffit pas. Phase 2 self-play risquée"
    echo "    sur cette base ; envisager hybrid + D2 combiné."
else
    echo "    FLAT — même le squelette ne débloque pas. Probable bug pipeline"
    echo "    ou archi v2 fondamentalement inadaptée à ce dataset. Debug."
fi
echo "=========================================================="
