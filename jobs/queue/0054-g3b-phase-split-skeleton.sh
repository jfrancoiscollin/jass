#!/usr/bin/env bash
# id: 0054-g3b-phase-split-skeleton
# description: G3b du docs/archives/SCAN_METHODOLOGY_GAP.md. Re-train pattern v2
#              hybrid base-3 + extras (G3a) AVEC phase split MG/EG sur le
#              squelette uniquement (bias, man, king, balance, king_pst).
#              Patterns restent mono-phase en v5.
#
# Hypothèse testée : G1-G3a flat, donc ni optimizer, ni labels, ni
# feature engineering ne sont la racine. Reste l'hypothèse Scan-spécifique
# "phase awareness" : Scan stocke chaque feature en 2 weights (MG/EG)
# interpolés par game_stage. Sans split, une eval mono-phase doit faire
# la moyenne (homme avancé vaut +50 ouverture / +200 finale → réseau
# trivial qui apprend la moyenne).
#
# G3b minimal : phase split sur le squelette uniquement (~108 weights
# nouveaux : bias_eg + man_eg + king_eg + balance_eg + king_pst_eg[50]).
# Patterns mono-phase parce que les doubler en MG/EG = 2× la taille du
# fichier et risque d'overfit. Si squelette phase split ne bouge rien,
# patterns phase split serait probablement pareil.
#
# Decision gate :
#   rate vs v5 d10 ≥ 0.30 → archi viable, G4 self-play en main propre.
#   ∈ [0.10, 0.30]        → progrès net, considérer G3b-full (patterns
#                          phase split aussi) ou direct G4.
#   < 0.10                → phase awareness skeleton n'est PAS la racine
#                          non plus. **CONCLUSION DIAG COMPLETE :
#                          supervised cheap a épuisé toutes les hypothèses
#                          cheap accessibles. Pattern axis frozen
#                          jusqu'à G4 commit ou nouveau leverage.**
#
# expected_duration: ~3-4h sur 4 vCPU CCX23.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0054-g3b-phase-split-skeleton"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "dataset: $DATASET"
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
echo "=== train pattern v2 HYBRID base-3 + extras + phase split — G3b ==="
OUT_JPAT="$ART/pattern-v2-g3b.jpat"
START_TRAIN=$(date +%s)
python3 tools/train_pattern.py \
    --data           "$DATASET" \
    --out            "$OUT_JPAT" \
    --patterns       v2 \
    --hybrid \
    --extras \
    --phase-split \
    --pattern-base   3 \
    --init-man       100 \
    --init-king      300 \
    --optimizer      lbfgs \
    --epochs         30 \
    --lr             1.0 \
    --lambda         0.5 \
    --score-scale    0.01 \
    --weight-decay   1e-5 \
    --grad-clip      0 \
    --lbfgs-max-iter 20 \
    --lbfgs-history  10 \
    --lbfgs-early-stop-patience 5 \
    --symmetry \
    --num-seeds      3 \
    --seed           42 \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

ls -lh "$OUT_JPAT"

echo
echo "=== bench vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$OUT_JPAT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$OUT_JPAT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$OUT_JPAT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""; RATE_V7_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
[ -f "$ART/bench-vs-v7-d10.log" ] && RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0054 G3b PATTERN v2 + phase split skeleton VERDICT"
echo "=========================================================="
echo "  train wall:        ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted:    $RATE_HC"
echo "  vs v5 d6 / d10:    $RATE_V5_D6 / $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 d10:         $RATE_V6_D10"
[ -n "$RATE_V7_D10" ] && echo "  vs v7 d10:         $RATE_V7_D10"
echo
echo "  References (pattern v2 supervised paths) :"
echo "    0046 Phase 1 pure       : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0047 Phase 1 quiet data : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0048 D1 hybrid base-5   : 0/18 hc, 6/54 d6, 0/54 d10"
echo "    0049 D2 hybrid base-3   : 0/18 hc, 1.5/54 d6, 0/54 d10"
echo "    0051 G1 LBFGS           : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0052 G2 distillation v7 : 0/18 hc, 0/54 d6, 0/54 d10"
echo "    0053 G3a king PST+bal   : 0/18 hc, 0/54 d6, 0/54 d10"
echo
echo "  Decision (per docs/archives/SCAN_METHODOLOGY_GAP.md §G3b, post-révision) :"
if   awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.30) }'; then
    echo "    PHASE AWARENESS WAS THE BOTTLENECK — archi viable, baseline"
    echo "    pour G4 self-play TD-leaf."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    PROGRÈS NET — phase split skeleton aide. Considérer G3b-full"
    echo "    (patterns phase split aussi) ou G4 self-play."
elif awk -v r="$RATE_V5_D10" 'BEGIN { exit !(r >= 0.05) }'; then
    echo "    PROGRÈS MARGINAL — phase awareness ajoute peu. Décision"
    echo "    difficile : G3b-full risquée vs abandon."
else
    echo "    FLAT — diagnostic chain G1-G3b complète, aucune variante"
    echo "    supervised cheap ne débloque l'archi pattern v2."
    echo "    CONCLUSION FERME : abandon pattern axis pour cette session."
    echo "    Reste seulement G4 self-play TD-leaf (€20-40, 3-4 sem,"
    echo "    risqué) à essayer plus tard si on commit le budget."
fi
echo "=========================================================="
