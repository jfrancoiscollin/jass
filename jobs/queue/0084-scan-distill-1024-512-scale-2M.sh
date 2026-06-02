#!/usr/bin/env bash
# id: 0084-scan-distill-1024-512-scale-2M
# description: Phase G.3 step 2 — scale data sur 1024-512 v11.
#
# 0083 a montré 1024-512 = vs Scan 0.194 (vs 0.111 pour 512-256, +75%).
# Ratio data/params actuel = 1M/1.45M = 0.69 (sous-saturé). Scale data
# pour atteindre ratio sain (1.5-3.0) devrait pousser vs Scan plus loin.
#
# Datasets disponibles (Scan-distill manquant pour 2 sur 3) :
#   * v8 1M (0056) → DÉJÀ distilled dans 0078 (réutilisé)
#   * v7 1M (0050) → à distiller via Scan d12
#   * master 372K (0014) → à distiller via Scan d12
# Total ~2.37M positions Scan-distilled.
#
# Decision gate :
#   * 1024-512 sur 2.37M vs Scan > 0.25 → scale continue (5M extract gen-data)
#   * vs Scan ∈ [0.20, 0.25] → marginal gain, ship v11 baseline 2.37M
#   * vs Scan < 0.20 → data plateau, cascading self-play prochain
#
# expected_duration: ~2-3h wall :
#   * relabel v7 1M @ d12 × 8 procs (~35 min)
#   * relabel master 372K @ d12 × 8 procs (~15 min)
#   * train 1024-512 sur 2.37M (~20-30 min, scales linearly)
#   * bench × 4 adversaires + Scan (~30-45 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0084-scan-distill-1024-512-scale-2M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V11_1024=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)

# Source datasets
V8_DISTILLED=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
V7_DATASET=/root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/v7-quiet-pv-1M.bin
MASTER_DATASET=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -f "$V8_DISTILLED" ] || { echo "ABORT: v8 distilled missing"; exit 3; }
[ -f "$V7_DATASET" ]   || { echo "ABORT: v7 raw dataset missing"; exit 3; }
[ -f "$MASTER_DATASET" ] || { echo "ABORT: master dataset missing"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"

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

# Helper : relabel a dataset via Scan d12, 8 parallel workers, merge shards
relabel_dataset() {
    local SRC="$1"
    local OUT="$2"
    local NAME="$3"
    local TOTAL=$(python3 -c "
import struct
with open('$SRC','rb') as f: raw = f.read()
print(struct.unpack_from('<I', raw, 4)[0])
")
    local NWORKERS=$(nproc)
    local SHARD_SIZE=$(( TOTAL / NWORKERS + 1 ))
    echo "Relabelling $NAME ($TOTAL records) via $NWORKERS workers × $SHARD_SIZE positions"

    local START=$(date +%s)
    local PIDS=()
    for ((w=0; w<NWORKERS; w++)); do
        local OFFSET=$(( w * SHARD_SIZE ))
        python3 tools/relabel_with_scan.py \
            --in "$SRC" --out "$ART/${NAME}-shard-${w}.bin" \
            --scan "$SCAN_BIN" --depth 12 --start "$OFFSET" \
            --max-records "$SHARD_SIZE" --timeout 60 \
            --newgame-every 50 --progress-every 10000 \
            > "$ART/${NAME}-shard-${w}.log" 2>&1 &
        PIDS+=($!)
    done
    for pid in "${PIDS[@]}"; do
        wait "$pid" || { echo "ABORT: $NAME worker $pid failed"; return 6; }
    done
    local SEC=$(( $(date +%s) - START ))
    echo "$NAME relabel : ${SEC}s ($(python3 -c "print(round($SEC/60,1))") min)"

    # Merge shards
    python3 - <<EOF
import struct
from pathlib import Path
out = Path("$OUT")
shards = sorted(Path("$ART").glob("$NAME-shard-*.bin"))
total = 0; buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n; buffers.append(raw[8:])
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged {len(shards)} shards → {out} ({total} records)", flush=True)
EOF
}

# Step 1 : relabel v7 1M
echo
echo "=========================================================="
echo "=== Step 1 : relabel v7 dataset 1M Scan d12 ==="
echo "=========================================================="
V7_DISTILLED="$ART/v7-distilled-1M.bin"
relabel_dataset "$V7_DATASET" "$V7_DISTILLED" "v7"

# Step 2 : relabel master 372K
echo
echo "=========================================================="
echo "=== Step 2 : relabel master 372K Scan d12 ==="
echo "=========================================================="
MASTER_DISTILLED="$ART/master-distilled.bin"
relabel_dataset "$MASTER_DATASET" "$MASTER_DISTILLED" "master"

# Step 3 : merge all 3 distilled datasets
echo
echo "=========================================================="
echo "=== Step 3 : merge 3 distilled datasets ==="
echo "=========================================================="
MERGED="$ART/v11-distilled-2M.bin"
python3 - <<EOF
import struct
from pathlib import Path
sources = ["$V8_DISTILLED", "$V7_DISTILLED", "$MASTER_DISTILLED"]
total = 0; buffers = []
for s in sources:
    raw = Path(s).read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from('<I', raw, 4)[0]
    total += n; buffers.append(raw[8:])
out = Path("$MERGED")
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged → {out} ({total} records)", flush=True)
EOF

# Sanity check : scores distribution
python3 -c "
import struct, statistics
with open('$MERGED','rb') as f: raw = f.read()
n = struct.unpack_from('<I', raw, 4)[0]
scores = [struct.unpack_from('<i', raw, 8+i*38+33)[0] for i in range(min(n,5000))]
print(f'merged dataset: {n} records, first 5000 scores: '
      f'mean={statistics.mean(scores):.1f} std={statistics.stdev(scores):.1f} '
      f'range=[{min(scores)}, {max(scores)}]')
"

# Step 4 : train 1024-512 sur 2M+ distilled
echo
echo "=========================================================="
echo "=== Step 4 : train v11 1024-512 sur 2.37M ==="
echo "=========================================================="
ARCH_DIR="$ART/arch-1024-512"
mkdir -p "$ARCH_DIR"
START_T=$(date +%s)
python3 tools/train_v3.py \
    --data                "$MERGED" \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --archs               1024-512 \
    --encoding            halfmen \
    --epochs              30 \
    --batch               512 \
    --out-dir             "$ARCH_DIR" \
    2>&1 | tee "$ART/train.log"
T_SEC=$(( $(date +%s) - START_T ))

V12_Q="$ARCH_DIR/nnue-1024-512-q.bin"
python3 tools/quantize_mlp.py --in "$ARCH_DIR/nnue-1024-512.bin" --data "$MERGED" --out "$V12_Q" \
    2>&1 | tee "$ART/quantize.log"

# Step 5 : bench
echo
echo "=========================================================="
echo "=== bench v12 (1024-512 / 2.37M) vs Scan / v6 / v7 / v8 / v11 d10 ==="
echo "=========================================================="
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V12_Q" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$V12_Q" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$V12_Q" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$V12_Q" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V11_1024" ] && ./build/jass --benchmark-nnue-vs-nnue "$V12_Q" "$V11_1024" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v11-d10.log"
R_V11=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v11-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0084 v12 1024-512 + 2.37M SCALE-UP VERDICT"
echo "=========================================================="
echo "  train wall : ${T_SEC}s"
echo "  vs Scan d10 : $R_SCAN"
echo "  vs v6 d10   : $R_V6"
echo "  vs v7 d10   : $R_V7"
echo "  vs v8 d10   : $R_V8"
echo "  vs v11 (1024-512 / 1M) : $R_V11"
echo
echo "  Reference :"
echo "    v10 512-256 (1M, 0078) : vs Scan 0.111  vs v8 0.417"
echo "    v11 1024-512 (1M, 0083): vs Scan 0.194  vs v8 0.639"
echo
echo "  Decision :"
echo "    * v12 vs Scan > 0.25 → scale continue, gen-data 5M (0085)"
echo "    * vs Scan ∈ [0.20, 0.25] → marginal gain, ship v11 baseline 2.37M"
echo "    * vs Scan < 0.20 → data plateau, cascading self-play"
echo "=========================================================="
