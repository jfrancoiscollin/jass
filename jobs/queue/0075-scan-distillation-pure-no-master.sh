#!/usr/bin/env bash
# id: 0075-scan-distillation-pure-no-master
# description: Pure distillation Scan — train v10 SANS master, juste les
#              100K positions Scan-distilled. Diagnostic clé : si encore
#              output collapse, le bug n'est PAS la dilution master mais
#              quelque part dans le pipeline distillation lui-même
#              (capacité MLP, score parsing, conversion FEN, ou autre).
#
# Verdict 0074 a confirmé que master BCE seul ne suffit pas. Hypothèse
# nouvelle : master domine massivement (78% vs 22% distilled), tire
# l'eval vers WDL plat → distillation diluée.
#
# 0075 teste l'hypothèse extrême : **drop master entirely**.
#
# Si 0075 marche (v10 vs v8 > 0.50) → master dilution était le coupable
# Si 0075 reste cassé (50/54 no legal move) → bug ailleurs, debug profond
#
# Réutilise le dataset distillé 0073/0074 (pas besoin de re-relabel).
#
# expected_duration: ~10-15 min (juste train + bench, pas de relabel)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0075-scan-distillation-pure-no-master"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present at $SCAN_BIN"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

# Reuse the Scan-distilled dataset (3 possible sources, prefer most recent).
for CANDIDATE in \
    /root/jass/jobs/results/0074-scan-distillation-pilot-master-bce-fix/artefacts.src/v10-distilled-100K.bin \
    /root/jass/jobs/results/0073-scan-distillation-pilot/artefacts.src/v10-distilled-100K.bin
do
    if [ -f "$CANDIDATE" ]; then
        RELAB_SRC="$CANDIDATE"
        break
    fi
done
[ -n "${RELAB_SRC:-}" ] || { echo "ABORT: no distilled dataset found"; exit 3; }

RELAB="$ART/v10-distilled-100K.bin"
cp "$RELAB_SRC" "$RELAB"
echo "Using distilled dataset : $RELAB_SRC ($(stat -c%s "$RELAB_SRC") bytes)"

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"

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

# Sanity check
python3 -c "
import struct, statistics
with open('$RELAB','rb') as f: raw = f.read()
n = struct.unpack_from('<I', raw, 4)[0]
scores = [struct.unpack_from('<i', raw, 8+i*38+33)[0] for i in range(min(n,1000))]
nonzero = sum(1 for s in scores if s != 0)
print(f'distilled dataset: {n} records, first 1000 nonzero={nonzero}/1000, '
      f'mean={statistics.mean(scores):.1f}, stdev={statistics.stdev(scores):.1f}, '
      f'range=[{min(scores)}, {max(scores)}]')
"

# --- PURE DISTILLATION TRAIN : NO --master-data ---
echo
echo "=========================================================="
echo "=== train v10 512-256 PURE distillation (no master) ==="
echo "=========================================================="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$RELAB" \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --archs               512-256 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

V10_BIN="$ART/nnue-512-256.bin"
V10_Q="$ART/nnue-512-256-q.bin"
python3 tools/quantize_mlp.py --in "$V10_BIN" --data "$RELAB" --out "$V10_Q" \
    2>&1 | tee "$ART/quantize.log"

# --- Bench ---
echo
echo "=========================================================="
echo "=== bench v10 pure vs Scan / v6 / v7 / v8 d10 ==="
echo "=========================================================="

python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V10_Q" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
RATE_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
RATE_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
RATE_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$V10_Q" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
RATE_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0075 PURE SCAN DISTILLATION VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s"
echo "  vs Scan d10 : $RATE_SCAN"
echo "  vs v6 d10   : $RATE_V6"
echo "  vs v7 d10   : $RATE_V7"
echo "  vs v8 d10   : $RATE_V8"
echo
echo "  Comparaison :"
echo "    0073 (master MSE buggy)  : vs Scan 0.028  vs v8 0.111"
echo "    0074 (master BCE fix)    : vs Scan 0.000  vs v8 0.194"
echo "    0075 (no master)         : vs Scan $RATE_SCAN  vs v8 $RATE_V8"
echo
echo "  Decision :"
echo "    * v10 vs v8 > 0.50 → master dilution était le bug, distillation marche"
echo "                          → scale-up 1M (0076)"
echo "    * v10 vs v8 ≈ 0074 → bug ailleurs (pipeline, capacité, FEN, score parsing)"
echo "                          → debug profond / repivoter"
echo "=========================================================="
