#!/usr/bin/env bash
# id: 0078-scan-distill-1M-mlp-scaleup
# description: Phase G.2 — scale-up distillation MLP. Relabel full 1M v8
#              dataset via Scan d12, puis train deux variantes archi
#              (256-128 + 512-256) pour départager capacity vs data.
#
# Verdict 0076 a montré : MLP 256-128 sur 100K distilled = vs Scan 0.056,
# vs v8 0.167 (premier signal non-zéro). Direction confirmée mais data
# limitante. 0078 scale ×10 (1M).
#
# Expectation : ratio data/params devient sain pour 512-256 (1M / 362K
# = 2.76, comme v8). On sait que 512-256 capture mieux avec assez de
# data ; 256-128 reste safe baseline.
#
# Decision gate :
#   * meilleur vs v8 d10 > 0.55 → distillation marche, ship v10
#   * meilleur vs Scan > 0.20  → tue 400+ ELO du gap (-800 → -400)
#   * vs v8 ∈ [0.30, 0.55]     → progrès marginal, scale d12→d16 (0079)
#   * tout flat                 → distillation hit ceiling, retour MLP enrichi (B) ou (D)
#
# expected_duration: ~1h20min wall :
#   * relabel 1M × Scan d12 × 8 procs (~50-70 min)
#   * train 256-128 (~5-10 min)
#   * train 512-256 (~10-15 min)
#   * bench × 2 archis × 4 adversaires (~20 min)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8_DATA=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/v8-quiet-pv-1M.bin 2>/dev/null | head -1)
[ -n "$V8_DATA" ] && [ -f "$V8_DATA" ] || { echo "ABORT: v8 dataset not found"; exit 3; }

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

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

# Use FULL v8 dataset (1M records) as input ; no sampling.
RELAB="$ART/v10-distilled-1M.bin"

# --- Phase G.2.a : relabel 1M positions Scan d12, 8 parallel shards ---
echo
echo "=========================================================="
echo "=== Phase G.2.a : relabel 1M positions d12 sur 8 procs ==="
echo "=========================================================="
NWORKERS=$(nproc)
SHARD_SIZE=$(( 1000000 / NWORKERS + 1 ))
echo "Spawning $NWORKERS Scan workers × $SHARD_SIZE positions each"

START_REL=$(date +%s)
PIDS=()
for ((w=0; w<NWORKERS; w++)); do
    OFFSET=$(( w * SHARD_SIZE ))
    SHARD_OUT="$ART/shard-${w}.bin"
    SHARD_LOG="$ART/shard-${w}.log"
    python3 tools/relabel_with_scan.py \
        --in    "$V8_DATA" \
        --out   "$SHARD_OUT" \
        --scan  "$SCAN_BIN" \
        --depth 12 \
        --start "$OFFSET" \
        --max-records "$SHARD_SIZE" \
        --timeout 60 \
        --newgame-every 50 \
        --progress-every 10000 \
        > "$SHARD_LOG" 2>&1 &
    PIDS+=($!)
done

for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        echo "ABORT: worker $pid failed"
        for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
        exit 6
    fi
done
REL_SEC=$(( $(date +%s) - START_REL ))
echo "relabel wall : ${REL_SEC}s ($(python3 -c "print(round($REL_SEC/60,1))") min)"

# Merge shards.
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
print(f"merged {len(shards)} shards → {out_path} ({total} records)", flush=True)
EOF

# Sanity check
python3 -c "
import struct, statistics
with open('$RELAB','rb') as f: raw = f.read()
n = struct.unpack_from('<I', raw, 4)[0]
scores = [struct.unpack_from('<i', raw, 8+i*38+33)[0] for i in range(min(n,1000))]
nonzero = sum(1 for s in scores if s != 0)
print(f'distilled 1M : {n} records, first 1000 nonzero={nonzero}/1000, '
      f'mean={statistics.mean(scores):.1f}, stdev={statistics.stdev(scores):.1f}')
assert nonzero >= 800, f'too many zero ({nonzero}/1000)'
"

# --- Phase G.2.b : train MLP 256-128 + 512-256 sur 1M distilled ---
RESULTS=""
for ARCH in 256-128 512-256; do
    echo
    echo "=========================================================="
    echo "=== train MLP $ARCH PURE distillation sur 1M ==="
    echo "=========================================================="
    ARCH_DIR="$ART/arch-$ARCH"
    mkdir -p "$ARCH_DIR"
    START_T=$(date +%s)
    python3 tools/train_v3.py \
        --data                "$RELAB" \
        --wdl-scale           400 \
        --bce-scale           50000 \
        --archs               "$ARCH" \
        --encoding            halfmen \
        --epochs              30 \
        --batch               512 \
        --out-dir             "$ARCH_DIR" \
        2>&1 | tee "$ART/train-$ARCH.log"
    T_SEC=$(( $(date +%s) - START_T ))

    BIN="$ARCH_DIR/nnue-$ARCH.bin"
    QUANT="$ARCH_DIR/nnue-$ARCH-q.bin"
    python3 tools/quantize_mlp.py --in "$BIN" --data "$RELAB" --out "$QUANT" \
        2>&1 | tee "$ART/quantize-$ARCH.log"

    echo "=== bench $ARCH vs Scan / v6 / v7 / v8 d10 ==="
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$QUANT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$ARCH-vs-scan-d10.log"
    R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-scan-d10.log" | head -1 | awk '{print $3}')

    [ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V6" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v6-d10.log"
    R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V7" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v7-d10.log"
    R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v8-d10.log"
    R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    RESULTS+="  $ARCH (train ${T_SEC}s) : vs Scan $R_SCAN  vs v6 $R_V6  vs v7 $R_V7  vs v8 $R_V8"$'\n'
done

echo
echo "=========================================================="
echo "       0078 SCAN DISTILL 1M MLP SCALE-UP VERDICT"
echo "=========================================================="
echo "  relabel wall : ${REL_SEC}s ($(python3 -c "print(round($REL_SEC/60,1))") min)"
echo
echo "$RESULTS"
echo
echo "  Comparaison 100K → 1M (256-128) :"
echo "    100K : vs Scan 0.056  vs v8 0.167"
echo "    1M   : voir ci-dessus"
echo
echo "  Decision :"
echo "    * meilleur vs v8 > 0.55 → distillation marche, ship v10"
echo "    * meilleur vs Scan > 0.20 → tue 400+ ELO du gap"
echo "    * vs v8 ∈ [0.30, 0.55] → progrès marginal, scale d12 → d16 (0079)"
echo "    * tout flat → distillation ceiling, repivot (B)/(D)"
echo "=========================================================="
