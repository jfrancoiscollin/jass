#!/usr/bin/env bash
# id: 0090-small-arch-sweep-movetime
# description: Phase A — arch sweep small NNUE pour vrai gain en time control.
#
# Verdict 0089 : v11 (1024-512) atteint 10 plies à 500ms, v8 (512-256)
# 13 plies, Scan 19.5 plies. v11 vs v8 à movetime = 0.426 (v11 PERD).
# Le plafond est l'eval cost MLP — small arch = more depth = more ELO.
#
# Calcul : 128-64 optimisé (~6-8M NPS) ≈ Scan NPS-parity (8.1M).
# 192-96 intermédiaire, 256-128 référence v8 archi.
#
# Mesures :
#   * Bench fixed-d10 vs Scan + v8/v11 (référence, pour situer le "fake gain")
#   * Bench MOVETIME=500ms vs Scan + v8/v11 (vraie mesure)
#   * NPS via 10 positions sample
#
# Decision :
#   * Meilleur en movetime > 0.05 vs Scan → ship comme v15 baseline
#   * Si 128-64 ≈ Scan rate vs 256-128 → confirme depth = key
#   * Si tous flat en movetime → inference SIMD optim absolument requis
#
# expected_duration: ~1.5-2.5h wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0090-small-arch-sweep-movetime"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
RELAB_1M=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$RELAB_1M" ] || { echo "ABORT: 0078 distilled 1M not found"; exit 3; }

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

# Sweep 3 archs sur 1M Scan-distilled
RESULTS=""
for ARCH in 128-64 192-96 256-128; do
    ARCH_DIR="$ART/arch-$ARCH"
    mkdir -p "$ARCH_DIR"
    echo
    echo "=========================================================="
    echo "=== train $ARCH PURE Scan-distillation sur 1M ==="
    echo "=========================================================="
    START_T=$(date +%s)
    python3 tools/train_v3.py \
        --data                "$RELAB_1M" \
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
    python3 tools/quantize_mlp.py --in "$BIN" --data "$RELAB_1M" --out "$QUANT" \
        2>&1 | tee "$ART/quantize-$ARCH.log"

    # --- Mesure NPS (10 positions sample) ---
    echo "=== NPS measurement $ARCH ==="
    python3 - <<EOF | tee "$ART/nps-$ARCH.log"
import struct, subprocess, re, random, statistics
from pathlib import Path
MASTER = "/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw"
NNUE = "$QUANT"
raw = Path(MASTER).read_bytes()
total = struct.unpack_from('<I', raw, 4)[0]
rng = random.Random(42)
idx = sorted(rng.sample(range(total), 10))
def fen(wm, wk, bm, bk, stm):
    parts = ['W' if stm == 0 else 'B']
    def squares(bb): return [i+1 for i in range(50) if (bb >> i) & 1]
    w = ','.join([str(s) for s in sorted(squares(wm))] + [f'K{s}' for s in sorted(squares(wk))])
    b = ','.join([str(s) for s in sorted(squares(bm))] + [f'K{s}' for s in sorted(squares(bk))])
    return f"{parts[0]}:W{w}:B{b}"
p = subprocess.Popen(['./build/jass', '--nnue', NNUE],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write("hello\n"); p.stdin.flush()
while True:
    if p.stdout.readline().startswith('ready'): break
depths=[]; nodes=[]
for k, i in enumerate(idx):
    off = 8 + i * 38
    wm, wk, bm, bk = struct.unpack_from('<QQQQ', raw, off)
    stm = raw[off+32]
    p.stdin.write(f"position fen {fen(wm,wk,bm,bk,stm)}\n")
    p.stdin.write("go movetime 500\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('bestmove'):
            m = re.search(r'depth=(\d+).*nodes=(\d+)', l)
            if m:
                depths.append(int(m.group(1))); nodes.append(int(m.group(2)))
            break
p.stdin.write("quit\n"); p.stdin.flush(); p.wait(timeout=5)
print(f"$ARCH : median depth={statistics.median(depths)}  median nodes={statistics.median(nodes)}  median NPS={statistics.median(nodes)*2:.0f}")
EOF

    # --- Bench fixed d10 vs Scan + v8 + v11 (référence "fake") ---
    echo "=== bench $ARCH fixed-d10 ==="
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$QUANT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$ARCH-vs-scan-d10.log"
    R_SCAN_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-scan-d10.log" | head -1 | awk '{print $3}')

    ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v8-d10.log"
    R_V8_D10=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    # --- Bench MOVETIME=500ms vs Scan + v8 (VRAIE mesure) ---
    echo "=== bench $ARCH movetime 500ms ==="
    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$QUANT" \
        --movetime 0.5 --pairs 3 \
        2>&1 | tee "$ART/bench-$ARCH-vs-scan-mt500.log"
    R_SCAN_MT=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-scan-mt500.log" | head -1 | awk '{print $3}')

    ./build/jass --benchmark-nnue-vs-nnue "$QUANT" "$V8" 32 3 1 500 \
        2>&1 | tee "$ART/bench-$ARCH-vs-v8-mt500.log"
    R_V8_MT=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$ARCH-vs-v8-mt500.log" 2>/dev/null | head -1 | awk '{print $3}')

    RESULTS+="  $ARCH (train ${T_SEC}s) : vs Scan d10=$R_SCAN_D10 mt500=$R_SCAN_MT  vs v8 d10=$R_V8_D10 mt500=$R_V8_MT"$'\n'
done

echo
echo "=========================================================="
echo "       0090 SMALL ARCH SWEEP MOVETIME VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Reference (movetime 500ms, mesuré 0088) :"
echo "    v11 (1024-512) vs Scan : 0.009  vs v8 : 0.426"
echo "    v8  (512-256)  vs Scan : ~0.05 (estim)"
echo
echo "  Decision :"
echo "    * meilleur mt500 vs Scan > 0.05 → ship comme v15 baseline"
echo "    * 128-64 ≈ NPS Scan → depth-parity, vrai test"
echo "    * tous flat → inference SIMD optim absolument requis"
echo "=========================================================="
