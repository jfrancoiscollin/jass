#!/usr/bin/env bash
# id: 0087-master-opening-targeted-augmentation
# description: Augmentation chirurgicale ciblée — master high-ELO opening
#              positions Scan-distilled, ajouté au v11 baseline.
#
# Diagnostic 0085 a montré : 40% des drift losses surviennent en OPENING
# (30-40 pièces), 22% en midgame (22-29). Le v8 dataset (extrait quiet-PV)
# privilégie midgame stable → sous-représente opening.
#
# Pourquoi 0087 ≠ 0084 (qui avait dégradé) :
#   * 0084 : ajout master+v7 INDIFFÉREMMENT (toutes phases mélangées) → dilution
#   * 0086 : v11 self-play data → biaisé vers v11's quirks → no signal
#   * 0087 : SURGICAL — opening positions only, high-ELO (2000+) only.
#            Cible précisément le bucket faible.
#
# Pipeline :
#   1. Load master-2000.jnnw (370K records, humans ≥2000 ELO)
#   2. Filter : piece_count >= 30 (opening / early midgame, where 62%
#      des drift losses arrivent)
#   3. Scan-relabel à d12, 8 workers
#   4. COMBINE avec v8 1M Scan-distilled (de 0078) — pas remplacer
#   5. Train v14 = 1024-512 sur dataset combiné ~1.1-1.2M
#   6. Bench vs Scan + v6/v7/v8/v11
#
# Decision gate :
#   * v14 vs Scan > 0.25 → augmentation opening unlock, scale (0088)
#   * v14 vs v11 > 0.55 → cumulative gain confirmé
#   * tout < v11 → opening augmentation ne porte pas, MLP infra plafonnée
#
# expected_duration: ~2-3h wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0087-master-opening-targeted-augmentation"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V11" ] && [ -f "$V11" ] || { echo "ABORT: v11 not found"; exit 3; }

MASTER_2000=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-2000.jnnw
[ -f "$MASTER_2000" ] || { echo "ABORT: master-2000 not found"; exit 3; }

V8_DISTILLED=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$V8_DISTILLED" ] || { echo "ABORT: v8 distilled (0078) not found"; exit 3; }

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

# --- Phase 1 : filter master to opening positions (piece_count >= 30) ---
echo
echo "=========================================================="
echo "=== Phase 1 : filter master-2000 to opening (>=30 pieces) ==="
echo "=========================================================="
OPENING_FILTERED="$ART/master-opening.jnnw"
python3 - <<EOF
import struct
from pathlib import Path
raw = Path("$MASTER_2000").read_bytes()
assert raw[:4] == b"JNNW"
total = struct.unpack_from("<I", raw, 4)[0]
print(f"input master-2000 : {total} records", flush=True)

# Count pieces from bbs (4× uint64 wm/wk/bm/bk)
def popcount64(x):
    x = x - ((x >> 1) & 0x5555555555555555)
    x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333)
    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0F
    return (x * 0x0101010101010101 & 0xFFFFFFFFFFFFFFFF) >> 56

kept = bytearray()
n_kept = 0
phase_hist = {"40-30": 0, "29-22": 0, "21-15": 0, "14-8": 0, "7-2": 0}
for i in range(total):
    off = 8 + i * 38
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", raw, off)
    pc = popcount64(wm) + popcount64(wk) + popcount64(bm) + popcount64(bk)
    if pc >= 40-9 and pc <= 40:    phase_hist["40-30"] += 1
    elif pc >= 22:                 phase_hist["29-22"] += 1
    elif pc >= 15:                 phase_hist["21-15"] += 1
    elif pc >= 8:                  phase_hist["14-8"] += 1
    else:                          phase_hist["7-2"] += 1
    if pc >= 30:
        kept.extend(raw[off:off+38])
        n_kept += 1
print(f"phase histogram: {phase_hist}", flush=True)
print(f"kept (>=30 pieces) : {n_kept} records", flush=True)
out = Path("$OPENING_FILTERED")
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", n_kept))
    f.write(bytes(kept))
EOF

# --- Phase 2 : Scan-relabel filtered opening positions ---
echo
echo "=========================================================="
echo "=== Phase 2 : Scan-relabel opening positions ==="
echo "=========================================================="
OPENING_DISTILLED="$ART/master-opening-scan-distilled.bin"
N_OPENING=$(python3 -c "
import struct
with open('$OPENING_FILTERED','rb') as f: raw = f.read()
print(struct.unpack_from('<I', raw, 4)[0])
")
NWORKERS=$(nproc)
SHARD_SIZE=$(( N_OPENING / NWORKERS + 1 ))
echo "Relabelling $N_OPENING opening positions × $NWORKERS workers × $SHARD_SIZE"

START_REL=$(date +%s)
PIDS=()
for ((w=0; w<NWORKERS; w++)); do
    OFFSET=$(( w * SHARD_SIZE ))
    python3 tools/relabel_with_scan.py \
        --in "$OPENING_FILTERED" --out "$ART/op-shard-${w}.bin" \
        --scan "$SCAN_BIN" --depth 12 --start "$OFFSET" \
        --max-records "$SHARD_SIZE" --timeout 60 \
        --newgame-every 50 --progress-every 5000 \
        > "$ART/op-shard-${w}.log" 2>&1 &
    PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
    wait "$pid" || { echo "ABORT: relabel worker $pid failed"; exit 6; }
done
REL_SEC=$(( $(date +%s) - START_REL ))

python3 - <<EOF
import struct
from pathlib import Path
out = Path("$OPENING_DISTILLED")
shards = sorted(Path("$ART").glob("op-shard-*.bin"))
total = 0; buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n; buffers.append(raw[8:])
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged distilled opening → {out} ({total} records)", flush=True)
EOF
echo "relabel wall : ${REL_SEC}s"

# --- Phase 3 : combine v8 1M distilled + opening distilled ---
echo
echo "=========================================================="
echo "=== Phase 3 : merge v8 distilled + master opening distilled ==="
echo "=========================================================="
COMBINED="$ART/v14-train-combined.bin"
python3 - <<EOF
import struct
from pathlib import Path
out = Path("$COMBINED")
total = 0; buffers = []
for src in ["$V8_DISTILLED", "$OPENING_DISTILLED"]:
    raw = Path(src).read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from('<I', raw, 4)[0]
    total += n; buffers.append(raw[8:])
    print(f"  {src}: {n} records", flush=True)
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"combined → {out} ({total} records)", flush=True)
EOF

# --- Phase 4 : train v14 = 1024-512 sur combined ---
echo
echo "=========================================================="
echo "=== Phase 4 : train v14 1024-512 sur combined ==="
echo "=========================================================="
ARCH_DIR="$ART/arch-1024-512"
mkdir -p "$ARCH_DIR"
START_T=$(date +%s)
python3 tools/train_v3.py \
    --data "$COMBINED" \
    --wdl-scale 400 --bce-scale 50000 \
    --archs 1024-512 --encoding halfmen \
    --epochs 30 --batch 512 \
    --out-dir "$ARCH_DIR" \
    2>&1 | tee "$ART/train.log"
T_SEC=$(( $(date +%s) - START_T ))

V14_Q="$ARCH_DIR/nnue-1024-512-q.bin"
python3 tools/quantize_mlp.py --in "$ARCH_DIR/nnue-1024-512.bin" --data "$COMBINED" --out "$V14_Q" \
    2>&1 | tee "$ART/quantize.log"

# --- Phase 5 : bench ---
echo
echo "=========================================================="
echo "=== bench v14 vs Scan / v6 / v7 / v8 / v11 d10 ==="
echo "=========================================================="
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V14_Q" \
    --depth 10 --pairs 3 \
    --dump-games-dir "$ART/games-vs-scan" \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$V14_Q" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$V14_Q" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$V14_Q" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

./build/jass --benchmark-nnue-vs-nnue "$V14_Q" "$V11" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v11-d10.log"
R_V11=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v11-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

# Optional : run loss phase analysis to confirm opening drift reduced
if [ -d "$ART/games-vs-scan" ]; then
    echo
    echo "=== Loss phase diagnostic on v14 (compare vs v12 0085) ==="
    python3 tools/analyze_loss_by_pieces.py \
        --games-dir "$ART/games-vs-scan" \
        --jass ./build/jass --nnue "$V14_Q" \
        --eval-threshold 200 \
        2>&1 | tee "$ART/loss-phase-analysis.log"
fi

echo
echo "=========================================================="
echo "       0087 v14 = MASTER-OPENING AUGMENTATION VERDICT"
echo "=========================================================="
echo "  relabel wall : ${REL_SEC}s"
echo "  train wall   : ${T_SEC}s"
echo "  vs Scan d10 : $R_SCAN"
echo "  vs v6 d10   : $R_V6"
echo "  vs v7 d10   : $R_V7"
echo "  vs v8 d10   : $R_V8"
echo "  vs v11 (baseline) : $R_V11"
echo
echo "  Reference :"
echo "    v11 (1M v8, 0083) : vs Scan 0.194  vs v8 0.639"
echo "    v12 (6.5M v8+v7+master, 0084) : vs Scan 0.111 (régressé)"
echo "    v13 (500K v11-selfplay, 0086) : vs Scan 0.028 (régressé)"
echo
echo "  Decision :"
echo "    * v14 vs Scan > 0.25 → opening augmentation unlock, scale (0088)"
echo "    * v14 vs v11 > 0.55 → cumulative gain confirmé"
echo "    * v14 ≈ v11 → augmentation neutre, ship v11"
echo "    * v14 < v11 → opening data nuit aussi, MLP infra plafonnée définitivement"
echo "=========================================================="
