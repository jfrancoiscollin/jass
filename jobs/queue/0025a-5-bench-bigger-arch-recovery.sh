#!/usr/bin/env bash
# id: 0025a-5-bench-bigger-arch-recovery
# description: Recovery du 0025a-4 (OOM sur 2048-1024). Les .bin de
#              512-256 et 1024-512 existent déjà — on quantize + bench
#              ces deux-là vs v5 pour avoir le verdict sans relancer
#              le training. 2048-1024 reste hors-scope (trop gros
#              pour les 15 GB du host).
#
#              Lecture (rate Cycle 9 v5 = 0.500 à depth 10, ref) :
#                rate > 0.55 → bigger arch dépasse v5 sur le même
#                              corpus 0010 1M → l'archi était le
#                              bottleneck, pas la donnée.
#                rate ≈ 0.50 → archi équivalente, pas le bottleneck.
#                rate < 0.45 → bigger overfits sur 1M.
#
# expected_duration: ~30-50 min sur 4 vCPU CCX23 (quant rapide,
#                    deux benchs head-to-head dominent le wall).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0025a-5-bench-bigger-arch-recovery"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

BIG_DIR="/root/jass/jobs/results/0025a-4-train-bigger-arch/artefacts"
DATASET="/root/jass/jobs/results/0010-gen-data-depth20-1M-smallbox/artefacts.src/depth20-1M.bin"
V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

[ -d "$BIG_DIR" ] || { echo "ABORT: 0025a-4 artefacts dir not found"; exit 3; }
[ -f "$DATASET" ] || { echo "ABORT: $DATASET not found"; exit 3; }
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

echo "=== inputs ==="
ls -lh "$BIG_DIR"/nnue-*.bin
echo "v5: $V5"
echo "dataset for quant calibration: $DATASET"

echo "=== rebuilding jass ==="
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

declare -A RATES_D6 RATES_D10
for arch in 512-256 1024-512; do
    BIN="$BIG_DIR/nnue-${arch}.bin"
    QOUT="$ART/nnue-${arch}-q.bin"
    if [ ! -f "$BIN" ]; then
        echo "  skip $arch — $BIN missing"
        continue
    fi

    echo
    echo "=== quantising $arch ==="
    python3 tools/quantize_mlp.py --in "$BIN" --data "$DATASET" --out "$QOUT" \
        2>&1 | tee "$ART/quant-${arch}.log"
    [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "  quant failed for $arch"; continue; }

    echo "=== bench $arch vs v5, depth 6, 3 pairs ==="
    ./build/jass --benchmark-nnue-vs-nnue "$QOUT" "$V5" 6 3 \
        2>&1 | tee "$ART/bench-${arch}-d6.log"
    RATES_D6[$arch]=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-${arch}-d6.log" | head -1 | awk '{print $3}')

    echo "=== bench $arch vs v5, depth 10, 3 pairs ==="
    ./build/jass --benchmark-nnue-vs-nnue "$QOUT" "$V5" 10 3 \
        2>&1 | tee "$ART/bench-${arch}-d10.log"
    RATES_D10[$arch]=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-${arch}-d10.log" | head -1 | awk '{print $3}')
done

echo
echo "=========================================================="
echo "       0025a-5 BIGGER ARCH RECOVERY VERDICT"
echo "=========================================================="
echo "  (score rate from bigger-arch's POV, depth 10 is the signal)"
for arch in 512-256 1024-512; do
    d6=${RATES_D6[$arch]:-N/A}
    d10=${RATES_D10[$arch]:-N/A}
    echo "  $arch  vs v5 :  d6=$d6  d10=$d10"
done
echo
echo "  References :"
echo "    Cycle 9 (512-256 on v5-labelled 100K) vs v5 : d10 = 0.500"
echo "    Reading: rate >0.55 → archi est le bottleneck"
echo "             rate ≈0.50 → archi neutre, autre cause"
echo "             rate <0.45 → overfit sur 1M"
echo "=========================================================="
