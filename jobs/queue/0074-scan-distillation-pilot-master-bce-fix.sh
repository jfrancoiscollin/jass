#!/usr/bin/env bash
# id: 0074-scan-distillation-pilot-master-bce-fix
# description: Paradigm shift (G) — distillation depuis Scan, pilot 100K
#              v2 avec config master loss corrigée.
#
# Le run 0073 a régressé (v10 vs Scan = 0.028 vs baseline v8 = 0.05).
# Cause identifiée : config training erronée pour le dataset master :
#   --master-loss mse --master-lam 1.0  ← FAUX
# Le master JNNW a score=0 partout (WDL pur). MSE sur score=0 sur
# 300K positions enseigne au MLP "prédis 0 toujours" → output
# collapse, 50/54 games perdues par "no legal move from Jass".
#
# Fix : --master-loss bce --master-lam 0.0 (comme dans le job v8 0056).
# Master contribue uniquement via le signal WDL (BCE), pas MSE.
#
# Réutilise le dataset Scan-distilled de 0073 (déjà sur le runner box,
# le relabel a marché : 100K positions d12 en 4.4 min). Si absent
# (artefacts purgés), re-relabel.
#
# expected_duration: ~30-45 min (skip relabel si dataset présent)
#   * train v10 512-256 sur dataset distillé corrigé : ~5 min
#   * bench vs Scan + v6/v7/v8 d10 : ~10-15 min
#   * (fallback) relabel 100k d12 × 8 procs : +5 min si nécessaire
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0074-scan-distillation-pilot-master-bce-fix"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
    echo "Scan binary not found at $SCAN_BIN — installing from rhalbersma/scan."
    SCAN_SRC=/root/jass-scan-src
    if [ ! -d "$SCAN_SRC" ]; then
        git clone --depth=1 https://github.com/rhalbersma/scan.git "$SCAN_SRC" \
            || { echo "ABORT: git clone scan failed"; exit 3; }
    fi
    mkdir -p /root/jass-scan
    cp "$SCAN_SRC/scan_linux" "$SCAN_BIN"
    chmod +x "$SCAN_BIN"
    cp -r "$SCAN_SRC/data"     /root/jass-scan/data     2>/dev/null || true
    cp    "$SCAN_SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

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

# Reuse the Scan-distilled dataset from 0073 if present.
RELAB_0073=/root/jass/jobs/results/0073-scan-distillation-pilot/artefacts.src/v10-distilled-100K.bin
RELAB="$ART/v10-distilled-100K.bin"
if [ -f "$RELAB_0073" ]; then
    echo "Reusing 0073 distilled dataset : $RELAB_0073 ($(stat -c%s "$RELAB_0073") bytes)"
    cp "$RELAB_0073" "$RELAB"
else
    echo "0073 distilled dataset missing — re-running relabel pipeline"
    # Extract sample
    SAMPLE="$ART/v8-sample-100K.bin"
    python3 - <<EOF
import struct, random
from pathlib import Path
raw = Path("$V8_DATA").read_bytes()
assert raw[:4] == b"JNNW"
total = struct.unpack_from("<I", raw, 4)[0]
N = min(100000, total)
rng = random.Random(42)
idx = sorted(rng.sample(range(total), N))
out = Path("$SAMPLE")
with out.open("wb") as f:
    f.write(b"JNNW")
    f.write(struct.pack("<I", N))
    for i in idx:
        off = 8 + i * 38
        f.write(raw[off:off+38])
print(f"wrote {out} ({N} records)", flush=True)
EOF
    NWORKERS=$(nproc)
    SHARD_SIZE=$(( 100000 / NWORKERS + 1 ))
    PIDS=()
    for ((w=0; w<NWORKERS; w++)); do
        OFFSET=$(( w * SHARD_SIZE ))
        python3 tools/relabel_with_scan.py \
            --in "$SAMPLE" --out "$ART/shard-${w}.bin" \
            --scan "$SCAN_BIN" --depth 12 --start "$OFFSET" \
            --max-records "$SHARD_SIZE" --timeout 60 --newgame-every 50 \
            --progress-every 2000 > "$ART/shard-${w}.log" 2>&1 &
        PIDS+=($!)
    done
    for pid in "${PIDS[@]}"; do wait "$pid" || { echo "ABORT: worker failed"; exit 6; }; done
    python3 - <<EOF
import struct
from pathlib import Path
out_path = Path("$RELAB")
shards = sorted(Path("$ART").glob("shard-*.bin"))
total = 0; buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n; buffers.append(raw[8:])
with out_path.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged → {out_path} ({total} records)", flush=True)
EOF
fi

# Sanity check on relab dataset.
python3 -c "
import struct
with open('$RELAB','rb') as f: raw = f.read()
n = struct.unpack_from('<I', raw, 4)[0]
scores = [struct.unpack_from('<i', raw, 8+i*38+33)[0] for i in range(min(n,1000))]
nonzero = sum(1 for s in scores if s != 0)
import statistics
print(f'relab: {n} records, first 1000 scores nonzero={nonzero}/1000, '
      f'mean={statistics.mean(scores):.1f}, stdev={statistics.stdev(scores):.1f}, '
      f'range=[{min(scores)}, {max(scores)}]')
assert nonzero >= 800, f'too many zero scores ({nonzero}/1000)'
"

# --- Train v10 512-256 — FIXED master loss config ---
echo
echo "=========================================================="
echo "=== train v10 512-256 (master BCE, scan-distilled MSE) ==="
echo "=========================================================="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$RELAB" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          0.0 \
    --master-loss         bce \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  2000000 \
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
echo "=== bench v10 vs Scan / v6 / v7 / v8 d10 ==="
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
echo "       0074 SCAN DISTILLATION (MASTER BCE FIX) VERDICT"
echo "=========================================================="
echo "  train wall : ${TRAIN_SEC}s"
echo "  vs Scan d10 : $RATE_SCAN"
echo "  vs v6 d10   : $RATE_V6"
echo "  vs v7 d10   : $RATE_V7"
echo "  vs v8 d10   : $RATE_V8"
echo
echo "  Comparaison 0073 (master MSE buggy) :"
echo "    vs Scan : 0.028 → ?"
echo "    vs v8   : 0.111 → ?"
echo
echo "  Decision gate :"
echo "    * v10 vs v8 > 0.55 → distillation fonctionne, scale-up 1M @ d16 (0075)"
echo "    * v10 vs Scan > 0.10 (vs 0.028 buggy) → master fix a aidé"
echo "    * tout < seuil → capacity limit OU bug autre, debug"
echo "=========================================================="
