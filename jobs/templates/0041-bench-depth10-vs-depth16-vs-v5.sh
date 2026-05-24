#!/usr/bin/env bash
# id: 0041-bench-depth10-vs-depth16-vs-v5
# description: Verdict de l'hypothèse "low-depth + WDL bat high-depth"
#              transposée à draughts. Compare tête-à-tête :
#                * NNUE trained on 1M @ depth 10 (de 0040)
#                * v5 baseline (de 0018, trained on 0010 1M @ depth 20
#                  mais labeller Linear pre-Cycle-8)
#                * Si dispo : NNUE trained on 1M @ depth 16 (de 0035)
#
#              Décision :
#                depth10 > v5 par +10+ ELO  → free lunch méthodologique,
#                                              futurs cycles à depth 10.
#                depth10 ≈ v5                → on garde depth 16-20
#                                              pour la qualité par
#                                              position.
#                depth10 << v5               → confirmé: en draughts, la
#                                              précision du score compte
#                                              plus qu'en chess. Reste
#                                              à depth élevée.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0041-bench-depth10-vs-depth16-vs-v5"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DEPTH10=$(ls -t /root/jass/jobs/results/0040-train-cycle9-1M-depth10/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V5=$(    ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
DEPTH16=$(ls -t /root/jass/jobs/results/0035-train-cycle9-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -n "$DEPTH10" ] && [ -f "$DEPTH10" ] || { echo "ABORT: depth-10 NNUE not found (0040)"; exit 3; }
[ -n "$V5" ]      && [ -f "$V5" ]      || { echo "ABORT: v5 NNUE not found (0018)";     exit 3; }

echo "depth10 NNUE (0040): $DEPTH10"
echo "v5       NNUE (0018): $V5"
if [ -n "$DEPTH16" ] && [ -f "$DEPTH16" ]; then
    echo "depth16 NNUE (0035): $DEPTH16"
else
    echo "depth16 NNUE: NOT AVAILABLE (0035 not run yet — skipping that match)"
fi

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== match A : depth10 (1M v5-labelled) vs v5, depth 10, 3 pairs ==="
./build/jass --benchmark-nnue-vs-nnue "$DEPTH10" "$V5" 10 3 \
    2>&1 | tee "$ART/match-depth10-vs-v5.log"
RATE_A=$(grep -oE 'score rate: [0-9.]+' "$ART/match-depth10-vs-v5.log" | head -1 | awk '{print $3}')

RATE_B=""
if [ -n "$DEPTH16" ] && [ -f "$DEPTH16" ]; then
    echo
    echo "=== match B : depth10 (0040) vs depth16 (0035), depth 10, 3 pairs ==="
    ./build/jass --benchmark-nnue-vs-nnue "$DEPTH10" "$DEPTH16" 10 3 \
        2>&1 | tee "$ART/match-depth10-vs-depth16.log"
    RATE_B=$(grep -oE 'score rate: [0-9.]+' "$ART/match-depth10-vs-depth16.log" | head -1 | awk '{print $3}')
fi

echo
echo "=========================================================="
echo "       0041 DEPTH-10 LABELLING VERDICT"
echo "=========================================================="
echo "  depth10 vs v5:      rate=$RATE_A   (score depth10 POV)"
[ -n "$RATE_B" ] && echo "  depth10 vs depth16: rate=$RATE_B   (score depth10 POV)"
echo
echo "  Reading match A:"
if   awk -v r="$RATE_A" 'BEGIN { exit !(r > 0.55) }'; then
    echo "    SOLID GAIN — depth 10 + WDL signal > v5 baseline."
    echo "    Free lunch méthodologique : futurs cycles à depth 10,"
    echo "    ~2-3× le débit gen-data sans perte de qualité."
elif awk -v r="$RATE_A" 'BEGIN { exit !(r >= 0.50) }'; then
    echo "    NEUTRAL — depth 10 équivalent à v5. Économie de compute"
    echo "    sans dégradation. Bascule sur depth 10 pour les volumes."
elif awk -v r="$RATE_A" 'BEGIN { exit !(r >= 0.45) }'; then
    echo "    SLIGHT LOSS — la précision du score compte un peu en"
    echo "    draughts. Rester à depth 14-16 (compromis)."
else
    echo "    HARD LOSS — depth 10 insuffisant en draughts. Garder"
    echo "    depth 18-20 pour les futurs cycles. Le free lunch chess"
    echo "    ne transpose pas."
fi
echo "=========================================================="
