#!/usr/bin/env bash
# id: 0073-scan-distillation-pilot
# description: Paradigm shift (G) — distillation depuis Scan, pilot 100K.
#
# Pipeline (3 phases) :
#   G.0 smoke    : 100 positions d12, single-process, verbose. Valide
#                  conversion FEN + parsing `info` lines + débit réel.
#                  ~5-10 min sur 1 core.
#   G.1 pilot    : 100k positions d12, 8 procs parallèles (8 shards de
#                  12.5k chacun). ~3-5h wall sur CCX33 8 vCPU.
#                  Train v10 512-256 sur dataset distillé. Bench vs Scan
#                  + v6/v7/v8 d10.
#
# Améliorations vs version initiale (note implémentation 2026-05-23) :
#   * depth d10 → d12  (meilleur compromis qualité/débit)
#   * archi 256-128 → 512-256  (entre v8 et v9, capacité raisonnable)
#   * lambda blend → MSE pure 1.0  (label score propre, pas besoin WDL)
#   * 1 process Scan → 8 parallèles  (~8× speedup wall)
#   * new-game per-position → tous les 50 (préserve TT, ~+30% débit)
#   * Scan = install pre-built binary depuis rhalbersma/scan repo (pas
#     de make/build — le repo contient scan_linux pré-compilé).
#   * score = float pawn units × 100 (Scan emits "score=-0.04", c'est
#     -4 cp ; le bug du 1er run était l'absence de × 100, scores=0)
#
# Decision gate G.1 :
#   * v10 vs v8 d10 > 0.55  → distillation fonctionne, Phase G.2 = 1M @ d16
#   * v10 vs Scan d10 > 0.20 → capture significative, scale-up
#   * tout < seuil          → capacity limit 512-256, repivoter sur 1024-512
#
# expected_duration: ~4-6h wall total
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0073-scan-distillation-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

SCAN_BIN=/tmp/scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
    echo "Scan binary not found at $SCAN_BIN — installing from rhalbersma/scan."
    SCAN_SRC=/tmp/scan-src
    if [ ! -d "$SCAN_SRC" ]; then
        git clone --depth=1 https://github.com/rhalbersma/scan.git "$SCAN_SRC" \
            || { echo "ABORT: git clone scan failed"; exit 3; }
    fi
    # rhalbersma/scan ships the pre-built Linux binary + data/ + scan.ini
    # in the repo root — no rebuild needed.
    mkdir -p /tmp/scan
    cp "$SCAN_SRC/scan_linux" "$SCAN_BIN"
    chmod +x "$SCAN_BIN"
    cp -r "$SCAN_SRC/data"     /tmp/scan/data     2>/dev/null || true
    cp    "$SCAN_SRC/scan.ini" /tmp/scan/scan.ini 2>/dev/null || true
    [ -x "$SCAN_BIN" ] || { echo "ABORT: Scan install failed"; exit 3; }
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

# Extract a 100K sample from v8 dataset (deterministic seed=42).
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

# --- Phase G.0 : smoke 100 positions, single-process, verbose ---
echo
echo "=========================================================="
echo "=== Phase G.0 : smoke 100 positions d12 ==="
echo "=========================================================="
START_SMOKE=$(date +%s)
python3 tools/relabel_with_scan.py \
    --in   "$SAMPLE" \
    --out  "$ART/smoke-100-d12.bin" \
    --scan "$SCAN_BIN" \
    --depth 12 \
    --max-records 100 \
    --timeout 60 \
    --progress-every 25 \
    --newgame-every 50 \
    2>&1 | tee "$ART/smoke.log"
SMOKE_SEC=$(( $(date +%s) - START_SMOKE ))
SMOKE_RATE=$(python3 -c "print(round(100/max(${SMOKE_SEC},1),3))")
echo "smoke wall=${SMOKE_SEC}s  throughput=${SMOKE_RATE} pos/s/proc"
EST_PILOT_SEC=$(python3 -c "print(int(100000 / max(${SMOKE_RATE} * 8, 0.01)))")
echo "extrapolation pilot 100k × 8 procs = ${EST_PILOT_SEC}s ($(python3 -c "print(round($EST_PILOT_SEC/60))") min)"

# Sanity check : smoke output should have 100 records with non-zero scores.
python3 -c "
import struct
with open('$ART/smoke-100-d12.bin','rb') as f: raw = f.read()
assert raw[:4] == b'JNNW'
n = struct.unpack_from('<I', raw, 4)[0]
nonzero = sum(1 for i in range(n) if struct.unpack_from('<i', raw, 8+i*38+33)[0] != 0)
print(f'smoke records: {n} ; non-zero scores: {nonzero}')
assert n == 100, f'expected 100 records, got {n}'
assert nonzero >= 30, f'too many zero scores ({nonzero}/{n}) — score parsing likely broken'
"

# --- Phase G.1 : 100k @ d12, 8 parallel shards ---
echo
echo "=========================================================="
echo "=== Phase G.1 : relabel 100k positions d12 sur 8 procs ==="
echo "=========================================================="
NWORKERS=$(nproc)
SHARD_SIZE=$(( 100000 / NWORKERS + 1 ))
echo "Spawning $NWORKERS Scan workers × $SHARD_SIZE positions each"

START_REL=$(date +%s)
PIDS=()
for ((w=0; w<NWORKERS; w++)); do
    OFFSET=$(( w * SHARD_SIZE ))
    SHARD_OUT="$ART/shard-${w}.bin"
    SHARD_LOG="$ART/shard-${w}.log"
    python3 tools/relabel_with_scan.py \
        --in    "$SAMPLE" \
        --out   "$SHARD_OUT" \
        --scan  "$SCAN_BIN" \
        --depth 12 \
        --start "$OFFSET" \
        --max-records "$SHARD_SIZE" \
        --timeout 60 \
        --newgame-every 50 \
        --progress-every 2000 \
        > "$SHARD_LOG" 2>&1 &
    PIDS+=($!)
done

# Wait for all workers ; if any fails, kill the rest and abort.
for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        echo "ABORT: worker $pid failed"
        for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
        exit 6
    fi
done
REL_SEC=$(( $(date +%s) - START_REL ))
echo "relabel wall : ${REL_SEC}s ($(python3 -c "print(round($REL_SEC/60,1))") min)"

# Merge shards into single JNNW.
RELAB="$ART/v10-distilled-100K.bin"
python3 - <<EOF
import struct
from pathlib import Path
out_path = Path("$RELAB")
shards = sorted(Path("$ART").glob("shard-*.bin"))
total = 0
buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW", f"{s}: bad magic"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n
    buffers.append(raw[8:])
with out_path.open("wb") as f:
    f.write(b"JNNW")
    f.write(struct.pack("<I", total))
    for b in buffers:
        f.write(b)
print(f"merged {len(shards)} shards → {out_path} ({total} records)", flush=True)
EOF

# --- Phase G.2 : train v10 512-256 sur dataset distillé ---
echo
echo "=========================================================="
echo "=== Phase G.2 : train v10 512-256 sur dataset Scan-distillé ==="
echo "=========================================================="
START_TRAIN=$(date +%s)
python3 tools/train_v3.py \
    --data                "$RELAB" \
    --master-data         "$MASTER" \
    --master-weight       1.0 \
    --master-lam          1.0 \
    --master-loss         mse \
    --wdl-scale           400 \
    --bce-scale           50000 \
    --max-master-records  300000 \
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

# --- Phase G.3 : bench ---
echo
echo "=========================================================="
echo "=== Phase G.3 : bench v10 vs Scan / v6 / v7 / v8 d10 ==="
echo "=========================================================="

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
echo "  smoke wall (100 pos)  : ${SMOKE_SEC}s    rate=${SMOKE_RATE} pos/s/proc"
echo "  relabel wall (100k)   : ${REL_SEC}s ($(python3 -c "print(round($REL_SEC/60,1))") min, 8 procs)"
echo "  train wall            : ${TRAIN_SEC}s ($(python3 -c "print(round($TRAIN_SEC/60,1))") min)"
echo "  vs Scan d10           : $RATE_SCAN  (baseline jass v8 = ~0.05)"
echo "  vs v6 d10             : $RATE_V6"
echo "  vs v7 d10             : $RATE_V7"
echo "  vs v8 d10             : $RATE_V8"
echo
echo "  Decision gate G.1 :"
echo "    * v10 vs v8 > 0.55 → distillation FONCTIONNE, Phase G.2 = 1M @ d16 (job 0074)"
echo "    * v10 vs Scan > 0.20 → capture significative"
echo "    * tout < seuil → capacity limit 512-256, repivoter 1024-512 ou d16"
echo "=========================================================="
