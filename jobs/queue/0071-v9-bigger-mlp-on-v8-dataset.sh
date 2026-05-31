#!/usr/bin/env bash
# id: 0071-v9-bigger-mlp-on-v8-dataset
# description: v9 = MLPNetworkQ 1024-512 entraîné sur v8 dataset (1M
#              positions v7-labelled-d16, ratio master 1.0). Premier
#              palier de la roadmap NNUE post-paradigm-A-réfuté.
#
# Hypothèse : v8 = 256-128 plafonne. Bigger arch sur le même dataset
# devrait absorber plus de signal (option E de PARADIGM_SHIFT_OPTIONS).
# Risque overfit faible avec 1M positions + master mix.
#
# expected_duration: ~30-45 min sur 8 vCPU CCX33 :
#                    * train 1024-512 sur 1M × 30 epochs (~20 min)
#                    * quantize (~2 min)
#                    * bench vs handcrafted / v5 / v6 / v7 / v8 d10 3 seeds (~10 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0071-v9-bigger-mlp-on-v8-dataset"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

DATASET=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$DATASET" ] && [ -f "$DATASET" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

MASTER=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)
[ -n "$MASTER" ] && [ -f "$MASTER" ] || MASTER=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw 2>/dev/null | head -1)
[ -n "$MASTER" ] && [ -f "$MASTER" ] || { echo "ABORT: master sample not found"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset : $DATASET"
echo "master     : $MASTER"
echo "v5/v6/v7/v8 : $V5 / $V6 / $V7 / $V8"

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
echo "=== train v9 = MLPNetworkQ 1024-512 sur v8 dataset ==="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$DATASET" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  2000000 \
    --archs               1024-512 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || { echo "ABORT: train failed"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

BEST_BIN="$ART/nnue-1024-512.bin"
QUANT_OUT="$ART/nnue-1024-512-q.bin"

python3 tools/quantize_mlp.py --in "$BEST_BIN" --data "$DATASET" --out "$QUANT_OUT" \
    2>&1 | tee "$ART/quantize.log"

echo
echo "=== bench v9 (1024-512) vs handcrafted / v5 / v6 / v7 / v8 d10 3 seeds ==="
./build/jass --benchmark-nnue              "$QUANT_OUT"            2>&1 | tee "$ART/bench-vs-hc.log"
./build/jass --benchmark-nnue-vs-nnue      "$QUANT_OUT" "$V5" 10 3 2>&1 | tee "$ART/bench-vs-v5-d10.log"
[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V6" 10 3 2>&1 | tee "$ART/bench-vs-v6-d10.log"
[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V7" 10 3 2>&1 | tee "$ART/bench-vs-v7-d10.log"
[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT_OUT" "$V8" 10 3 2>&1 | tee "$ART/bench-vs-v8-d10.log"

RATE_HC=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-hc.log"     | head -1 | awk '{print $3}')
RATE_V5=$(    grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v5-d10.log" | head -1 | awk '{print $3}')
RATE_V6=""
[ -f "$ART/bench-vs-v6-d10.log" ] && RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" | head -1 | awk '{print $3}')
RATE_V7=""
[ -f "$ART/bench-vs-v7-d10.log" ] && RATE_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" | head -1 | awk '{print $3}')
RATE_V8=""
[ -f "$ART/bench-vs-v8-d10.log" ] && RATE_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0071 v9 = MLPNetworkQ 1024-512 VERDICT"
echo "=========================================================="
echo "  train wall:    ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs handcrafted: $RATE_HC"
echo "  vs v5 d10:      $RATE_V5"
echo "  vs v6 d10:      $RATE_V6"
echo "  vs v7 d10:      $RATE_V7"
echo "  vs v8 d10:      $RATE_V8"
echo
echo "  Comparaison (rate vs v6 d10, baseline historique) :"
echo "    v7 ~0.50  (équivalence avec son ancêtre)"
echo "    v8 ~0.50  (idem, non-transitif observé)"
echo "    v9 = $RATE_V6"
echo
echo "  Action :"
echo "    * vs v8 > 0.55 → v9 ships clairement, retag baseline"
echo "    * vs v8 ∈ [0.50, 0.55] → léger gain, ship + ajouter SMP avant v10"
echo "    * vs v8 ∈ [0.45, 0.50] → flat, bigger MLP plafonne pareil"
echo "                              passer direct à Lazy SMP comme leverage"
echo "    * vs v8 < 0.45 → régression overfit, baisser arch ou debug"
echo "=========================================================="
