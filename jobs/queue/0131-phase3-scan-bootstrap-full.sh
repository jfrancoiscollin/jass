#!/usr/bin/env bash
# id: 0131-phase3-scan-bootstrap-full
# description: Phase 3 vraie — relabel 1.5M master records avec Scan d10,
# clip ±5000cp (au lieu de 200K + d12 + clip ±2000 du pilot 0130).
#
# Hypothèses corrigées :
#  - 200K était trop peu (×25 moins que 0129 = 4.7M → coverage chute)
#  - Scan d12 produit des scores trop extrêmes (range [-9998, +9999])
#    → clip ±2000 perdait 30%+ d'information
#  - Scan d10 : scores plus tempérés, ~3× plus rapide que d12
#  - 1.5M : compromise volume/wall, coverage devrait remonter
#  - Clip ±5000 : garde 99% des scores
#
# Sizing estimé : 1.5M × d10 sur 8 cores ≈ 12-15 min relabel
#
# expected_duration: ~25-40 min wall total
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0131-phase3-scan-bootstrap-full"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master missing"; exit 3; }

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan binary"; exit 3; }

TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"
NCPU=$(nproc)

echo "=== host : $(hostname)  nproc: $NCPU ==="

echo
echo "=== Phase 0 : install python deps ==="
if ! python3 -c "import scipy, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"; mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages \
            --no-cache-dir --quiet scipy numpy && break
        sleep 5
    done
    rm -rf "$PIP_SCRATCH"
fi

echo
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

TARGET_N=1500000
echo
echo "=== Phase 2 : sub-sample master ${TARGET_N} records (seed=42) ==="
SAMPLE="$ART/master-sample-1500K.jnnw"
python3 - <<EOF
import struct, random
from pathlib import Path
raw = Path("$MASTER").read_bytes()
total = struct.unpack_from("<I", raw, 4)[0]
N = min($TARGET_N, total)
rng = random.Random(42)
idx = sorted(rng.sample(range(total), N))
out = Path("$SAMPLE")
with out.open("wb") as f:
    f.write(b"JNNW")
    f.write(struct.pack("<I", N))
    for i in idx:
        off = 8 + i * 38
        f.write(raw[off:off+38])
print(f"wrote {out} ({N} records)")
EOF

echo
echo "=== Phase 3 : Scan d10 relabel ${TARGET_N} en $NCPU shards parallèles ==="
SCAN_OUT="$ART/master-1500K-scan-d10.jnnw"
START_SCAN=$(date +%s)
NSHARDS=$NCPU
SHARD_SIZE=$(( TARGET_N / NSHARDS ))
SHARD_FILES=()
pids=()
for sh in $(seq 0 $((NSHARDS - 1))); do
    START=$(( sh * SHARD_SIZE ))
    OUT_SH="$ART/shard-${sh}.jnnw"
    SHARD_FILES+=("$OUT_SH")
    (
        python3 tools/relabel_with_scan.py \
            --in "$SAMPLE" --out "$OUT_SH" \
            --scan "$SCAN_BIN" --depth 10 \
            --start "$START" --max-records "$SHARD_SIZE" \
            --timeout 60 --newgame-every 50 \
            > "$ART/relabel-shard-${sh}.log" 2>&1
    ) &
    pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=$((fail+1)); done
[ "$fail" -eq 0 ] || { echo "ABORT: $fail shards failed"; exit 4; }
SCAN_WALL=$(( $(date +%s) - START_SCAN ))
echo "  scan relabel wall : ${SCAN_WALL}s ($(( SCAN_WALL / 60 ))m)"

python3 - <<EOF
import struct
from pathlib import Path
shards = [$(printf '"%s",' "${SHARD_FILES[@]}")]
total = 0
with open("$SCAN_OUT", 'wb') as out:
    out.write(b"JNNW"); out.write(struct.pack("<I", 0))
    for sh in shards:
        raw = Path(sh).read_bytes()
        n = struct.unpack_from('<I', raw, 4)[0]
        out.write(raw[8:8 + n * 38]); total += n
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} scan-labelled records → $SCAN_OUT")
EOF

echo
echo "=== Phase 4 : handcrafted skeleton aligné ==="
HC_OUT="$ART/master-1500K-handcrafted.jnnw"
./build-prod/jass --rewrite-scores-with-handcrafted "$SAMPLE" "$HC_OUT" \
    > "$ART/handcrafted.log" 2>&1
RC=${PIPESTATUS[0]}
[ "$RC" -eq 0 ] || { echo "ABORT: handcrafted"; exit 4; }

echo
echo "=== Phase 5 : train pattern hybride sur Scan-labels (clip ±5000) ==="
WEIGHTS_OUT="$ART/pattern_jass_v9_scan_full.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$SCAN_OUT" \
    --skeleton-data "$HC_OUT" \
    --out  "$WEIGHTS_OUT" \
    --target score --score-clip 5000 \
    --l2 1e-5 --max-iter 200 --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

echo
echo "=== Phase 6 : bench vs handcrafted (Gate 3) ==="
./build-prod/jass --benchmark-pattern-jass "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-vs-hc-d6.log"
RATE_HC=$(grep -oE 'PATTERN_JASS score rate: [0-9.]+' "$ART/bench-vs-hc-d6.log" | head -1 | awk '{print $4}')

echo
echo "=========================================================="
echo "       0131 PHASE 3 SCAN BOOTSTRAP FULL VERDICT"
echo "=========================================================="
echo "  scan relabel : ${SCAN_WALL}s (1.5M × d10 × 8 shards)"
echo "  train wall   : ${TRAIN_SEC}s"
echo
echo "  Historique pattern hybride :"
echo "    0129 (v15 NNUE label, 4.7M, clip 2000)   : 0.667"
echo "    0130 (Scan d12,       200K, clip 2000)   : 0.083"
echo "    0131 (Scan d10,       1.5M, clip 5000)   : $RATE_HC"
echo
if [ -n "$RATE_HC" ]; then
    python3 - <<EOF
import math
rate = float("$RATE_HC")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else float('inf')
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.75:
    print(f"  → GATE 3 PASS — Phase 4 self-play à planifier")
elif rate > 0.667:
    print(f"  → progrès vs 0129 ({rate:.3f} > 0.667), Scan labels aident")
elif rate >= 0.50:
    print(f"  → rate ~0129 ({rate:.3f}) : Scan ≈ v15 NNUE comme labeller")
else:
    print(f"  → regress vs 0129 : Scan distill ne marche pas même avec params corrigés")
EOF
fi
echo "=========================================================="
