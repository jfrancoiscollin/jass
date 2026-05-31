#!/usr/bin/env bash
# id: 0073-scan-distillation-pilot
# description: Paradigm shift (G) — distillation depuis Scan, pilot 100K.
#
# Génère un dataset 100K positions relabellisées par Scan d10 (sample
# du v8 dataset), entraîne v10-small (256-128 baseline) sur ces nouvelles
# labels, bench vs Scan + v6/v7/v8.
#
# Pilot 100K @ d10 = ~3-6h wall (Scan rapide à d10, ~0.1-0.3s/pos).
# Si signal positif (v10 > v6 OU pearson Scan↔v10 élevée), Phase G.2
# scale-up à 1M @ d16 dans un job suivant (~24-48h compute).
#
# Decision gate :
#   * v10 vs Scan score rate > 0.20 → distillation FONCTIONNE, scale-up
#   * v10 vs v8 d10 > 0.55         → v10 > v8 dans notre famille, ship
#   * pearson v10 vs Scan > 0.85   → représentation bien apprise
#   * tout < seuil                 → capacity limit, repivoter sur 1024-512
#
# expected_duration: ~3-6h wall sur 8 vCPU CCX33 :
#                    * relabel 100K × Scan d10 (~3-5h)
#                    * train v10 256-128 (~10 min)
#                    * bench vs Scan + v6/v7/v8 d10 (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0073-scan-distillation-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

SCAN_BIN=/tmp/scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
    echo "Scan binary not found at $SCAN_BIN — attempting build."
    SCAN_SRC=/tmp/scan-src
    if [ ! -d "$SCAN_SRC" ]; then
        git clone --depth=1 https://github.com/rhalbersma/scan.git "$SCAN_SRC" \
            || { echo "ABORT: git clone scan failed"; exit 3; }
    fi
    mkdir -p /tmp/scan
    (cd "$SCAN_SRC" && make -j"$(nproc)" 2>&1 | tail -10)
    # rhalbersma/scan puts the binary in src/ as scan ; copy to expected loc.
    if [ -x "$SCAN_SRC/scan" ]; then
        cp "$SCAN_SRC/scan" "$SCAN_BIN"
        cp -r "$SCAN_SRC/data" /tmp/scan/data 2>/dev/null || true
        cp "$SCAN_SRC/scan.ini" /tmp/scan/scan.ini 2>/dev/null || true
    fi
    [ -x "$SCAN_BIN" ] || { echo "ABORT: Scan build failed"; exit 3; }
fi

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

MASTER=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)
[ -n "$MASTER" ] && [ -f "$MASTER" ] || MASTER=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw 2>/dev/null | head -1)

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 dataset : $V8_DATA"
echo "scan       : $SCAN_BIN"
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

# Phase G.1.a : extract a 100K sample from the v8 dataset (deterministic seed).
SAMPLE_100K="$ART/v8-sample-100K.bin"
python3 - <<EOF
import struct, random
from pathlib import Path
raw = Path("$V8_DATA").read_bytes()
assert raw[:4] == b"JNNW"
total = struct.unpack_from("<I", raw, 4)[0]
N = min(100000, total)
rng = random.Random(42)
idx = sorted(rng.sample(range(total), N))
out = Path("$SAMPLE_100K")
with out.open("wb") as f:
    f.write(b"JNNW")
    f.write(struct.pack("<I", N))
    for i in idx:
        off = 8 + i * 38
        f.write(raw[off:off+38])
print(f"wrote {out} ({N} records)", flush=True)
EOF

# Phase G.1.b : relabel via Scan d10.
echo
echo "=== relabel 100K positions via Scan d10 ==="
RELAB="$ART/v10-distilled-100K.bin"
START_REL=$(date +%s)
python3 tools/relabel_with_scan.py \
    --in    "$SAMPLE_100K" \
    --out   "$RELAB" \
    --scan  "$SCAN_BIN" \
    --depth 10 \
    --timeout 30 \
    --progress-every 500 \
    2>&1 | tee "$ART/relabel.log"
REL_SEC=$(( $(date +%s) - START_REL ))

# Phase G.1.c : train v10 256-128 on distilled dataset.
echo
echo "=== train v10 256-128 sur dataset distillé ==="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$RELAB" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  500000 \
    --archs               256-128 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ART" \
    2>&1 | tee "$ART/train.log"
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

V10_BIN="$ART/nnue-256-128.bin"
V10_Q="$ART/nnue-256-128-q.bin"

python3 tools/quantize_mlp.py --in "$V10_BIN" --data "$RELAB" --out "$V10_Q" \
    2>&1 | tee "$ART/quantize.log"

# Phase G.1.d : bench v10 vs Scan + v6/v7/v8 d10.
echo
echo "=== bench v10 vs Scan / v6 / v7 / v8 d10 ==="

# vs Scan : use calibrate_vs_scan.py for a proper match.
START_VS_SCAN=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass \
    --scan "$SCAN_BIN" \
    --nnue "$V10_Q" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
VS_SCAN_SEC=$(( $(date +%s) - START_VS_SCAN ))
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
echo "       0073 SCAN DISTILLATION PILOT VERDICT"
echo "=========================================================="
echo "  relabel wall :  ${REL_SEC}s ($(python3 -c "print(round($REL_SEC/60,1))") min)"
echo "  train wall   :  ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs Scan d10  :  $RATE_SCAN  (baseline jass v8 = ~0.05)"
echo "  vs v6 d10    :  $RATE_V6"
echo "  vs v7 d10    :  $RATE_V7"
echo "  vs v8 d10    :  $RATE_V8"
echo
echo "  Action :"
echo "    * v10 vs Scan > 0.20 → distillation FONCTIONNE, scale-up 1M @ d16 (0074)"
echo "    * v10 vs v8 > 0.55  → v10 > v8 dans la famille jass, ship v10"
echo "    * tout < seuil      → capacity limit 256-128, repivoter 1024-512"
echo "=========================================================="
