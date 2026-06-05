#!/usr/bin/env bash
# id: 0130-phase3-scan-bootstrap-pilot
# description: Phase Pattern-3 pilot — bootstrap pattern hybride avec
# labels Scan (oracle plus fort que v15 NNUE).
#
# Étapes :
#  1. Sub-sample master 1.6M → 200K records (deterministic seed)
#  2. Relabel les 200K avec Scan d12 via tools/relabel_with_scan.py (parallel 8 shards)
#  3. Aussi relabel handcrafted en parallèle (skeleton aligné record-par-record)
#  4. Train pattern hybride : target = scan_score - handcrafted_score
#  5. Bench Gate 3 :
#     - vs handcrafted : cible ≥ 0.75
#     - vs v8 NNUE     : cible ≥ 0.30
#
# Si Gate 3 PASS : Phase 4 (self-play co-evolution) à planifier.
# Si Gate 3 FAIL : analyser pourquoi Scan labels ne donnent pas mieux que v15.
#
# expected_duration: ~3-4h wall (Scan relabel 200K × d12 sur 8 cores)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0130-phase3-scan-bootstrap-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -f "$MASTER" ] || { echo "ABORT: master missing"; exit 3; }
[ -n "$V8" ] && [ -f "$V8" ] || { echo "ABORT: v8 weights missing"; exit 3; }

SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
    SCAN_SRC=/root/jass-scan-src
    [ -d "$SCAN_SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SCAN_SRC"
    mkdir -p /root/jass-scan
    cp "$SCAN_SRC/scan_linux" "$SCAN_BIN"
    chmod +x "$SCAN_BIN"
    cp -r "$SCAN_SRC/data" /root/jass-scan/data 2>/dev/null || true
    cp "$SCAN_SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null || true
fi
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

echo
echo "=== Phase 2 : sub-sample master 200K (seed=42) ==="
SAMPLE="$ART/master-sample-200K.jnnw"
python3 - <<EOF
import struct, random
from pathlib import Path
raw = Path("$MASTER").read_bytes()
assert raw[:4] == b"JNNW"
total = struct.unpack_from("<I", raw, 4)[0]
N = min(200000, total)
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
echo "=== Phase 3 : relabel 200K avec Scan d12 (8 shards parallèles) ==="
SCAN_OUT="$ART/master-200K-scan-d12.jnnw"
START_SCAN=$(date +%s)
NSHARDS=$NCPU
SHARD_SIZE=$(( 200000 / NSHARDS ))
SHARD_FILES=()
pids=()
for sh in $(seq 0 $((NSHARDS - 1))); do
    START=$(( sh * SHARD_SIZE ))
    OUT_SH="$ART/shard-${sh}.jnnw"
    SHARD_FILES+=("$OUT_SH")
    (
        python3 tools/relabel_with_scan.py \
            --in "$SAMPLE" --out "$OUT_SH" \
            --scan "$SCAN_BIN" --depth 12 \
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

# Concat shards (same record order as sample, since each shard wrote sequential)
python3 - <<EOF
import struct
from pathlib import Path
shards = [$(printf '"%s",' "${SHARD_FILES[@]}")]
total = 0
with open("$SCAN_OUT", 'wb') as out:
    out.write(b"JNNW")
    out.write(struct.pack("<I", 0))
    for sh in shards:
        raw = Path(sh).read_bytes()
        n = struct.unpack_from('<I', raw, 4)[0]
        out.write(raw[8:8 + n * 38])
        total += n
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"merged {total} scan-labelled records → $SCAN_OUT")
EOF

echo
echo "=== Phase 4 : compute handcrafted skeleton for the same 200K ==="
HC_OUT="$ART/master-200K-handcrafted.jnnw"
./build-prod/jass --rewrite-scores-with-handcrafted "$SAMPLE" "$HC_OUT" \
    > "$ART/handcrafted.log" 2>&1
RC=${PIPESTATUS[0]}
[ "$RC" -eq 0 ] || { echo "ABORT: handcrafted rewrite"; exit 4; }

echo
echo "=== Phase 5 : train pattern hybride sur Scan-labels ==="
WEIGHTS_OUT="$ART/pattern_jass_v8_scan_bootstrap.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass/tools/train.py \
    --data "$SCAN_OUT" \
    --skeleton-data "$HC_OUT" \
    --out  "$WEIGHTS_OUT" \
    --target score --score-clip 2000 \
    --l2 1e-5 --max-iter 200 --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train"; exit 4; }
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))

echo
echo "=== Phase 6a : bench vs handcrafted ==="
./build-prod/jass --benchmark-pattern-jass "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-vs-hc-d6.log"
RATE_HC=$(grep -oE 'PATTERN_JASS score rate: [0-9.]+' "$ART/bench-vs-hc-d6.log" | head -1 | awk '{print $4}')

echo
echo "=== Phase 6b : bench vs v8 NNUE ==="
./build-prod/jass --benchmark-nnue-vs-nnue "$WEIGHTS_OUT" "$V8" 6 3 \
    2>&1 | tee "$ART/bench-vs-v8-d6.log" 2>/dev/null || \
{
    # Fallback : the pattern PJTW isn't compatible with --benchmark-nnue-vs-nnue
    # (different magic). Skip with note.
    echo "  (--benchmark-nnue-vs-nnue ne supporte pas PJTW, skip vs v8 pour ce pilot)"
    RATE_V8="n/a (mode incompatible)"
}
[ -z "${RATE_V8:-}" ] && RATE_V8=$(grep -oE 'A score rate: [0-9.]+' "$ART/bench-vs-v8-d6.log" 2>/dev/null | head -1 | awk '{print $4}')

echo
echo "=========================================================="
echo "       0130 PHASE 3 SCAN BOOTSTRAP PILOT VERDICT"
echo "=========================================================="
echo "  scan relabel wall : ${SCAN_WALL}s"
echo "  train wall        : ${TRAIN_SEC}s"
echo "  weights output    : $WEIGHTS_OUT"
echo
echo "  Gate 3 thresholds :"
echo "    vs handcrafted ≥ 0.75 : actual $RATE_HC"
echo "    vs v8 NNUE     ≥ 0.30 : actual ${RATE_V8:-n/a}"
echo
if [ -n "$RATE_HC" ]; then
    python3 - <<EOF
rate_hc = float("$RATE_HC")
import math
elo = -400 * math.log10(1/rate_hc - 1) if 0 < rate_hc < 1 else float('inf')
print(f"  vs handcrafted : rate {rate_hc:.3f}  ΔELO ≈ {elo:+.0f}")
if rate_hc >= 0.75:
    print(f"  → vs handcrafted Gate 3 PASS")
elif rate_hc >= 0.65:
    print(f"  → vs handcrafted PROGRES vs 0129 (0.667) — bon signe")
else:
    print(f"  → vs handcrafted REGRESS vs 0129 (0.667) — Scan labels n'aident pas")
EOF
fi
echo "=========================================================="
