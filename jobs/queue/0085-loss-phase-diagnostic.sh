#!/usr/bin/env bash
# id: 0085-loss-phase-diagnostic
# description: Diagnostic post-hoc — où jass gagne/perd ses parties par
#              piece count phase ?
#
# Rejoue v12 (ou v11 fallback) vs Scan d10 3 pairs (54 games) AVEC dump
# per-game JSON (moves + FENs). Puis lance analyze_loss_by_pieces.py
# qui bucketize les wins/losses/draws par phase (piece count).
#
# Phases :
#   opening (30-40)  midgame (22-29)  late-mid (15-21)
#   endgame (8-14)   deep-eg (2-7)
#
# Sortie : table outcomes × phases, identifie quelle phase est la plus
# faible pour jass. Hypothèse à valider : losses concentrées en
# late-mid (15-21) ou endgame (8-14) ?
#
# expected_duration: ~30-60 min wall
#   * bench vs Scan d10 3 pairs (~15-30 min)
#   * analyze offline (~5-10 min sans eval drift, ~30 min avec)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0085-loss-phase-diagnostic"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

# Use v12 (0084) if available, else v11 (0083 1024-512)
V12=$(ls -t /root/jass/jobs/results/0084-scan-distill-1024-512-scale-2M/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
V11_1024=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)

if [ -n "$V12" ] && [ -f "$V12" ]; then
    BEST_MODEL="$V12"
    MODEL_TAG="v12-1024-512-2.37M"
elif [ -n "$V11_1024" ] && [ -f "$V11_1024" ]; then
    BEST_MODEL="$V11_1024"
    MODEL_TAG="v11-1024-512-1M"
else
    echo "ABORT: no v12/v11 1024-512 model found"; exit 3
fi

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"
echo "Using model : $BEST_MODEL ($MODEL_TAG)"

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

GAMES_DIR="$ART/games"
mkdir -p "$GAMES_DIR"

echo
echo "=========================================================="
echo "=== bench $MODEL_TAG vs Scan d10 3 pairs (dump games) ==="
echo "=========================================================="
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$BEST_MODEL" \
    --depth 10 --pairs 3 \
    --dump-games-dir "$GAMES_DIR" \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "=== analyze games by piece count phase (fast proxy) ==="
echo "=========================================================="
python3 tools/analyze_loss_by_pieces.py \
    --games-dir "$GAMES_DIR" \
    2>&1 | tee "$ART/analysis-fast.log"

echo
echo "=========================================================="
echo "=== analyze games with eval drift (slow, real diagnostic) ==="
echo "=========================================================="
python3 tools/analyze_loss_by_pieces.py \
    --games-dir "$GAMES_DIR" \
    --jass ./build/jass --nnue "$BEST_MODEL" \
    --eval-threshold 200 \
    2>&1 | tee "$ART/analysis-drift.log"

echo
echo "=========================================================="
echo "       0085 LOSS PHASE DIAGNOSTIC VERDICT"
echo "=========================================================="
echo "  Model      : $MODEL_TAG"
echo "  Score rate vs Scan d10 : $RATE"
echo "  See $ART/analysis-fast.log  (terminal/decision phase)"
echo "  See $ART/analysis-drift.log (eval-drift phase, plus précis)"
echo
echo "  Lecture suggérée :"
echo "    * Losses concentrées sur quelle phase ? = bucket à renforcer"
echo "    * Wins concentrées où ? = forces actuelles"
echo "    * Asymétrie L/W marquée → next step = target ce bucket"
echo "      (e.g. plus de positions endgame dans le training set, ou"
echo "       quiet-PV extract dans cette phase)"
echo "=========================================================="
