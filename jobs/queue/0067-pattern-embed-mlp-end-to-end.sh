#!/usr/bin/env bash
# id: 0067-pattern-embed-mlp-end-to-end
# description: Paradigm shift option (A) — Pattern indices → embeddings
#              dans une MLP end-to-end (PyTorch prototype).
#
# Hypothèse : les 13 hypothèses cheap pattern ont toutes utilisé une
# combinaison LINÉAIRE des lookup values (poids scalaires par bucket).
# Ici chaque pattern fournit un VECTEUR (embed_dim dims) via nn.Embedding ;
# les N vecteurs sont concaténés puis passés à un MLP non-linéaire.
# Beaucoup plus de degrés de liberté par pattern + interactions
# cross-pattern apprenables. Format proche du NNUE classique.
#
# Phase 1 (cette tâche) : Python-only prototype, train + pearson vs v7
# sur master positions (neutres). Pas de win-rate bench (pas de port C++).
#
# Decision gate :
#   pearson vs v7 (master positions) > 0.45 → signal qualitatif fort vs
#     0065 linear (0.28) et 0066 MLP-head (0.12). Port C++ justifié → JPAT v8.
#   pearson ∈ [0.30, 0.45]              → léger gain vs linear, ambigu.
#     Tester variantes (embed_dim, hidden) avant port C++.
#   pearson < 0.30                       → embedding paradigm n'apporte
#     rien. Paradigm shift cheap exhausté pour l'axe pattern. Pivoter
#     vers (B) MLPNetworkQ enrichi ou (D) AlphaZero.
#
# expected_duration: ~3-4h sur 8 vCPU CCX33 :
#                    * load 1M v8 dataset (~5 min)
#                    * Adam train 30 epochs × ~5 min/epoch (~2.5h)
#                    * pearson eval (~10 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0067-pattern-embed-mlp-end-to-end"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V7" ] && [ -f "$V7" ] || { echo "ABORT: v7 NNUE not found"; exit 3; }

MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER_SAMPLE" ] || MASTER_SAMPLE=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw
[ -f "$MASTER_SAMPLE" ] || { echo "ABORT: master sample not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset    : $V8_DATA"
echo "v7 reference  : $V7"
echo "master sample : $MASTER_SAMPLE"

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

# Use v2 pattern (8 verticals × 10 squares) → 3^10 = 59,049 buckets/pattern.
# v2 × embed_dim=4 → ~1.9M params (manageable for 1M dataset).
# v3 (12 squares) would explode to 17M params → overfit territory.
echo
echo "=== train pattern v2 embeddings end-to-end on v8 dataset ==="
OUT_PT="$ART/embed-v2-d4-h64.pt"
START_TRAIN=$(date +%s)
python3 tools/train_pattern_embed.py \
    --data         "$V8_DATA" \
    --out          "$OUT_PT" \
    --patterns     v2 \
    --embed-dim    4 \
    --mlp-hidden   64 \
    --epochs       30 \
    --batch        4096 \
    --lr           1e-3 \
    --lambda       0.7 \
    --score-scale  0.01 \
    --weight-decay 1e-5 \
    --val-frac     0.05 \
    --seed         42 \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
ls -lh "$OUT_PT"

echo
echo "=== pearson vs v7 (master positions, neutral sample) ==="
python3 tools/pattern_embed_correlation.py \
    --embed "$OUT_PT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
    2>&1 | tee "$ART/pearson-vs-v7.log"
PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-vs-v7.log" | head -1 | awk '{print $3}')

echo
echo "=== pearson vs v7 (v8 dataset positions, self-play biased) ==="
python3 tools/pattern_embed_correlation.py \
    --embed "$OUT_PT" --ref "$V7" --data "$V8_DATA" --n 1000 --seed 17 \
    2>&1 | tee "$ART/pearson-vs-v7-selfplay.log"
PEARSON_SP=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-vs-v7-selfplay.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0067 PATTERN EMBED MLP END-TO-END VERDICT"
echo "=========================================================="
echo "  train wall:                                  ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  pearson vs v7 (master, neutral):             $PEARSON"
echo "  pearson vs v7 (v8 dataset, self-play bias):  $PEARSON_SP"
echo
echo "  Direct A/B vs paradigm cousins :"
echo "    0065 (v3 linear,    v8 dataset) : pearson master ~0.28"
echo "    0066 (v3 MLP head,  v8 dataset) : pearson master ~0.12"
echo "    0067 (v2 embed+MLP, v8 dataset) : pearson master $PEARSON"
echo
if [ -n "$PEARSON" ] && awk -v p="$PEARSON" 'BEGIN { exit !(p >= 0.45) }'; then
    echo "    EMBEDDING UNLOCK — signal qualitatif fort vs linear/MLP-head."
    echo "    Port C++ (JPAT v8 format) justifié. Phase 2 = win-rate bench."
elif [ -n "$PEARSON" ] && awk -v p="$PEARSON" 'BEGIN { exit !(p >= 0.30) }'; then
    echo "    LÉGER GAIN vs linear (0.28). Tester variantes embed_dim/hidden"
    echo "    avant port C++."
else
    echo "    FLAT — embedding paradigm n'apporte rien non plus."
    echo "    L'axe pattern dans notre infra est définitivement exhausté."
    echo "    Pivoter vers (B) MLPNetworkQ enrichi ou (D) AlphaZero."
fi
echo "=========================================================="
