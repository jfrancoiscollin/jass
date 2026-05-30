#!/usr/bin/env bash
# id: 0061-bench-h3-bootstrap-alone
# description: (B) du plan post-H1+H3 verdict. Bench le pattern-bootstrap
#              de 0059 (pre-trained sur master games WDL, AVANT les 10
#              iter self-play qui ont dégradé son signal) seul, contre
#              handcrafted/v5/v6/v7. Compute pearson vs v7.
#
# Hypothèse : H1+H3 verdict 0059 a montré pearson 0.71 à iter 1 (juste
# après bootstrap) drift down à 0.58 à iter 10. Le self-play dégrade
# le signal. Le pre-train brut pourrait être le bon endpoint.
#
# Si le bootstrap-only sort un win-rate > 0 vs v6 d10, OR si le pearson
# vs v7 est nettement plus haut que ce qu'on a vu en self-play, on a
# isolé le bootstrap comme la composante critique → suite : H4 mobility
# ON TOP of bootstrap (job 0062 standby).
#
# expected_duration: ~10-15 min sur 8 vCPU CCX33 :
#                    * 5 benches × 18-54 games depth 6/10 (~5-10 min)
#                    * 1 pearson computation (~2 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0061-bench-h3-bootstrap-alone"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

BOOTSTRAP=$(ls -t /root/jass/jobs/results/0059-h1-h3-combined/artefacts.src/pattern-bootstrap.jpat 2>/dev/null | head -1)
[ -n "$BOOTSTRAP" ] && [ -f "$BOOTSTRAP" ] || { echo "ABORT: pattern-bootstrap.jpat from 0059 not found"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"
echo "bootstrap: $BOOTSTRAP ($(stat -c %s "$BOOTSTRAP") bytes)"
echo "v5/v6/v7: $V5 / ${V6:-<missing>} / ${V7:-<missing>}"
echo "pearson sample: $MASTER_SAMPLE"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

echo
echo "=== bench bootstrap vs handcrafted / v5 / v6 / v7 ==="
./build/jass --benchmark-nnue              "$BOOTSTRAP"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$BOOTSTRAP" "$V5"  6 3 2>&1 | tee "$ART/bench-vs-v5-d6.log"
./build/jass --benchmark-nnue-vs-nnue      "$BOOTSTRAP" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$BOOTSTRAP" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$BOOTSTRAP" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"

echo
echo "=== pearson bootstrap vs v7 (n=1000) ==="
PEARSON="-"
if [ -n "$V7" ]; then
    python3 tools/pattern_eval_correlation.py \
        --pattern "$BOOTSTRAP" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
        2>&1 | tee "$ART/pearson-vs-v7.log"
    PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-vs-v7.log" | head -1 | awk '{print $3}')
fi

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5_D6=$( grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d6.log"  | head -1 | awk '{print $3}')
RATE_V5_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6_D10=""; RATE_V7_D10=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
[ -f "$ART/bench-vs-v7-d10.log" ] && RATE_V7_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0061 BOOTSTRAP-PATTERN STANDALONE VERDICT"
echo "=========================================================="
echo "  pattern :          $BOOTSTRAP"
echo "  vs handcrafted:    $RATE_HC"
echo "  vs v5 d6 / d10:    $RATE_V5_D6 / $RATE_V5_D10"
[ -n "$RATE_V6_D10" ] && echo "  vs v6 d10:         $RATE_V6_D10"
[ -n "$RATE_V7_D10" ] && echo "  vs v7 d10:         $RATE_V7_D10"
echo "  pearson vs v7:     $PEARSON"
echo
echo "  Reference (0059 H1+H3 self-play loop) :"
echo "    iter 1 pearson vs v7: +0.7098 (just after bootstrap-trained)"
echo "    iter 10 pearson vs v7: +0.5823 (after 10 self-play iters)"
echo
echo "  Decision :"
if [ -n "$RATE_V6_D10" ] && awk -v r="$RATE_V6_D10" 'BEGIN { exit !(r >= 0.10) }'; then
    echo "    BOOTSTRAP ALONE WINS — pre-train master games suffit, le"
    echo "    self-play loop est inutile / nuisible. Ship pattern-bootstrap"
    echo "    OR scale-up bootstrap dataset (refresh Lidraughts)."
elif [ -n "$PEARSON" ] && awk -v r="$PEARSON" 'BEGIN { exit !(r > 0.70) }'; then
    echo "    PEARSON ÉLEVÉ ($PEARSON) sans win-rate — signal qualitatif"
    echo "    réel mais calibration manque. Suite : H4 mobility ON TOP de"
    echo "    bootstrap pour ajouter la feature structurelle manquante"
    echo "    (activate job 0062 standby)."
else
    echo "    BOOTSTRAP n'apporte rien vs self-play final — pas la"
    echo "    composante critique. Reste H4 seul ou H2 volume."
fi
echo "=========================================================="
