#!/usr/bin/env bash
# id: 0086-v11-selfplay-scan-distill-pilot
# description: Phase G.4 pilot — gen-data via v11 self-play, Scan-relabel.
#
# Verdict 0084 a montré : add master + v7-extract DATA HURT (vs Scan
# 0.194 → 0.111). Le distillation gagne quand la distribution data
# matche la baseline. v11 (1024-512 sur 1M v8) est la meilleure
# baseline → étendre AVEC v11-style data, pas master/v7.
#
# Pipeline :
#   1. gen-data via v11 self-play (PLAY_DEPTH=4, ~500K positions cheap)
#   2. Scan-relabel @ d12, 8 workers
#   3. Train v13 = 1024-512 sur ces 500K positions v11-selfplay-Scan-labelled
#   4. Bench vs Scan + v6/v7/v8/v11
#
# Si v13 vs v11 > 0.55 → Phase G.4 fonctionne, scale 2M (0087)
# Si v13 vs Scan > 0.25 → distillation v11→v13 = vrai unlock additionnel
# Si flat → data plateau définitif, MLP infra plafonnée à -250 ELO vs Scan
#
# Use EVAL_DEPTH=4 (cheap : on relabel avec Scan après, jass label
# inutile). PLAY_DEPTH=4 (idem que 0056). PV_EXTRACT=3 (idem).
#
# expected_duration: ~5-8h wall :
#   * gen-data 500K v11 self-play (~2-4h, 8 shards parallel)
#   * Scan-relabel 500K @ d12 (~20 min)
#   * train v13 1024-512 sur 500K (~15-25 min)
#   * bench (~30 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0086-v11-selfplay-scan-distill-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V11" ] && [ -f "$V11" ] || { echo "ABORT: v11 NNUE not found"; exit 3; }

NSHARDS=$(nproc)
RECORDS_TOTAL=500000
PER_SHARD=$(( (RECORDS_TOTAL + NSHARDS - 1) / NSHARDS ))
EVAL_DEPTH=4    # cheap : Scan relabel après, jass label inutile
PLAY_DEPTH=4
MAX_PLIES=200
SEED_BASE=86000
PV_EXTRACT=3

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v11 NNUE   : $V11"
echo "config     : NSHARDS=$NSHARDS  PER_SHARD=$PER_SHARD  EVAL_DEPTH=$EVAL_DEPTH  PLAY_DEPTH=$PLAY_DEPTH"

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

# --- Phase 1 : gen-data via v11 self-play ---
echo
echo "=========================================================="
echo "=== Phase 1 : gen-data 500K via v11 self-play ==="
echo "=========================================================="
START_GEN=$(date +%s)
pids=()
for shard in $(seq 1 $NSHARDS); do
    seed=$((SEED_BASE + shard))
    (
        START_SH=$(date +%s)
        ./build/jass --gen-data-wdl \
            "$PER_SHARD" \
            "$ART/shard-$shard.bin" \
            "$EVAL_DEPTH" "$PLAY_DEPTH" "$MAX_PLIES" "$seed" \
            --nnue "$V11" \
            --quiet-only \
            --pv-extract "$PV_EXTRACT" \
            > "$ART/shard-$shard.log" 2>&1
        rc=$?
        echo "$rc $(( $(date +%s) - START_SH ))" > "$ART/shard-$shard.result"
        exit $rc
    ) &
    pids+=($!)
    echo "  shard $shard launched as pid $! (seed $seed)"
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=$((fail + 1)); done
GEN_SEC=$(( $(date +%s) - START_GEN ))
[ "$fail" -eq 0 ] || { echo "ABORT: $fail/$NSHARDS shards failed"; exit 4; }
echo "gen-data wall : ${GEN_SEC}s ($(python3 -c "print(round($GEN_SEC/60,1))") min)"

# Merge shards
RAW="$ART/v11-selfplay-raw.bin"
python3 - <<EOF
import struct
from pathlib import Path
shards = sorted(Path("$ART").glob("shard-*.bin"))
total = 0; buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n; buffers.append(raw[8:])
out = Path("$RAW")
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged {len(shards)} shards → {out} ({total} records)", flush=True)
EOF

# --- Phase 2 : Scan-relabel ---
echo
echo "=========================================================="
echo "=== Phase 2 : Scan-relabel 500K @ d12 × 8 procs ==="
echo "=========================================================="
DISTILLED="$ART/v11-selfplay-scan-distilled.bin"
N_RECORDS=$(python3 -c "
import struct
with open('$RAW','rb') as f: raw = f.read()
print(struct.unpack_from('<I', raw, 4)[0])
")
SHARD_SIZE_REL=$(( N_RECORDS / NSHARDS + 1 ))
echo "Relabelling $N_RECORDS records × $NSHARDS workers × $SHARD_SIZE_REL positions"

START_REL=$(date +%s)
PIDS=()
for ((w=0; w<NSHARDS; w++)); do
    OFFSET=$(( w * SHARD_SIZE_REL ))
    python3 tools/relabel_with_scan.py \
        --in "$RAW" --out "$ART/rel-shard-${w}.bin" \
        --scan "$SCAN_BIN" --depth 12 --start "$OFFSET" \
        --max-records "$SHARD_SIZE_REL" --timeout 60 \
        --newgame-every 50 --progress-every 5000 \
        > "$ART/rel-shard-${w}.log" 2>&1 &
    PIDS+=($!)
done
for pid in "${PIDS[@]}"; do
    wait "$pid" || { echo "ABORT: relabel worker $pid failed"; exit 6; }
done
REL_SEC=$(( $(date +%s) - START_REL ))

python3 - <<EOF
import struct
from pathlib import Path
out = Path("$DISTILLED")
shards = sorted(Path("$ART").glob("rel-shard-*.bin"))
total = 0; buffers = []
for s in shards:
    raw = s.read_bytes()
    assert raw[:4] == b"JNNW"
    n = struct.unpack_from("<I", raw, 4)[0]
    total += n; buffers.append(raw[8:])
with out.open("wb") as f:
    f.write(b"JNNW"); f.write(struct.pack("<I", total))
    for b in buffers: f.write(b)
print(f"merged distilled → {out} ({total} records)", flush=True)
EOF

echo "relabel wall : ${REL_SEC}s"

# --- Phase 3 : train v13 = 1024-512 ---
echo
echo "=========================================================="
echo "=== Phase 3 : train v13 1024-512 sur 500K v11-selfplay-Scan ==="
echo "=========================================================="
ARCH_DIR="$ART/arch-1024-512"
mkdir -p "$ARCH_DIR"
START_T=$(date +%s)
python3 tools/train_v3.py \
    --data "$DISTILLED" \
    --wdl-scale 400 --bce-scale 50000 \
    --archs 1024-512 --encoding halfmen \
    --epochs 30 --batch 512 \
    --out-dir "$ARCH_DIR" \
    2>&1 | tee "$ART/train.log"
T_SEC=$(( $(date +%s) - START_T ))

V13_Q="$ARCH_DIR/nnue-1024-512-q.bin"
python3 tools/quantize_mlp.py --in "$ARCH_DIR/nnue-1024-512.bin" --data "$DISTILLED" --out "$V13_Q" \
    2>&1 | tee "$ART/quantize.log"

# --- Phase 4 : bench ---
echo
echo "=========================================================="
echo "=== bench v13 vs Scan / v6 / v7 / v8 / v11 d10 ==="
echo "=========================================================="
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V13_Q" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log"
R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')

[ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$V13_Q" "$V6" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v6-d10.log"
R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$V13_Q" "$V7" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v7-d10.log"
R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

[ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$V13_Q" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v8-d10.log"
R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

./build/jass --benchmark-nnue-vs-nnue "$V13_Q" "$V11" 10 3 1 0 \
    2>&1 | tee "$ART/bench-vs-v11-d10.log"
R_V11=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-v11-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0086 v13 V11-SELFPLAY-DISTILL PILOT VERDICT"
echo "=========================================================="
echo "  gen-data wall : ${GEN_SEC}s ($(python3 -c "print(round($GEN_SEC/60,1))") min)"
echo "  relabel wall  : ${REL_SEC}s"
echo "  train wall    : ${T_SEC}s"
echo "  vs Scan d10 : $R_SCAN"
echo "  vs v6 d10   : $R_V6"
echo "  vs v7 d10   : $R_V7"
echo "  vs v8 d10   : $R_V8"
echo "  vs v11 (1024-512 / 1M v8 Scan-distilled) : $R_V11"
echo
echo "  Reference :"
echo "    v11 1024-512 (1M v8, 0083) : vs Scan 0.194  vs v8 0.639"
echo
echo "  Decision :"
echo "    * v13 vs v11 > 0.55 → cascading marche, scale 2M (0087)"
echo "    * v13 vs Scan > 0.25 → vrai unlock additionnel"
echo "    * v13 < v11 → cascading dégrade, ship v11 comme baseline final"
echo "=========================================================="
