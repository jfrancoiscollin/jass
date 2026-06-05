#!/usr/bin/env bash
# id: 0121-pattern-jass-variant-C-kings
# description: Variant C — Phase Pattern-2 v3 : encoding 5-state qui
# inclut kings (empty/bm/bk/wm/wk). 8 patterns × 8 squares × 5^8 =
# 390 625 buckets/pattern × 8 = 3 125 000 buckets total (~12 MB).
#
# Hypothèse : la majorité des master positions ont des kings ; les
# exclure (Variant A et B) rend l'eval blind sur les endgames. Variant C
# inclut kings via 5-state, au prix d'un compte de buckets ×6.6.
#
# Run sequentiel après Variant B (0120). Compare aux A et B pour isoler
# l'effet "kings dans l'eval".
#
# expected_duration: ~1h-1h30 wall (3.1M weights → train + bench plus lourds)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0121-pattern-jass-variant-C-kings"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master missing : $MASTER"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
NCPU=$(nproc)

echo
echo "=== Phase 0 : install scipy if missing ==="
if ! python3 -c "import scipy, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages \
            --no-cache-dir --quiet scipy numpy && break
        sleep 5
    done
    rm -rf "$PIP_SCRATCH"
fi

echo
echo "=== Phase 1 : build prod (with pattern_jass_kings bridge) ==="
rm -rf build-prod
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : train v4 kings (target=score, 5-state) ==="
WEIGHTS_OUT="$ART/pattern_jass_v4_kings.pjtw"
START_TRAIN=$(date +%s)
python3 pattern_jass_kings/tools/train.py \
    --data "$MASTER" \
    --out  "$WEIGHTS_OUT" \
    --target score \
    --score-clip 2000 \
    --l2 1e-5 \
    --max-iter 200 \
    --scale 1000 \
    2>&1 | tee "$ART/train.log"
TRAIN_RC=${PIPESTATUS[0]}
TRAIN_SEC=$(( $(date +%s) - START_TRAIN ))
[ "$TRAIN_RC" -eq 0 ] || { echo "ABORT: train failed rc=$TRAIN_RC"; exit 4; }

echo
echo "=== Phase 3 : bench Gate 2 (kings) ==="
START_BENCH=$(date +%s)
./build-prod/jass --benchmark-pattern-jass-kings "$WEIGHTS_OUT" 6 3 \
    2>&1 | tee "$ART/bench-d6-pairs3.log"
BENCH_SEC=$(( $(date +%s) - START_BENCH ))

RATE=$(grep -oE 'PATTERN_JASS_KINGS score rate: [0-9.]+' "$ART/bench-d6-pairs3.log" | head -1 | awk '{print $4}')
VERDICT=$(grep -E "^GATE 2 " "$ART/bench-d6-pairs3.log" | head -1)

echo
echo "=========================================================="
echo "       0121 VARIANT C (kings 5-state) VERDICT"
echo "=========================================================="
echo "  vs 0118bis (wdl, 3-state, 8 patterns) : 0.000"
echo "  vs 0119    (score, 3-state, 8 patterns) : (see 0119)"
echo "  vs 0120    (score, 3-state, 12 patterns) : (see 0120)"
echo "  vs 0121    (score, 5-state, 8 patterns)  : $RATE"
echo "  $VERDICT"
echo
if [ -n "$RATE" ]; then
    python3 - <<EOF
import math
rate = float("$RATE")
elo = -400 * math.log10(1/rate - 1) if 0 < rate < 1 else (float('inf') if rate==1 else -float('inf'))
print(f"  rate {rate:.3f} = ΔELO ≈ {elo:+.0f} vs handcrafted")
if rate >= 0.55:
    print(f"  → VARIANT C PASS Gate 2. Inclure kings résout le pb.")
elif rate >= 0.35:
    print(f"  → VARIANT C partiel ({rate:.3f}).")
else:
    print(f"  → VARIANT C FAIL ({rate:.3f}).")
    print(f"     Si A, B, C tous failed → infra pattern marche sur Othello")
    print(f"     mais pas sur draughts. Hypothèse next : géométrie Scan-style")
    print(f"     12-square avec mask-shuffle (cf docs/SCAN_ARCHITECTURE §3).")
EOF
fi
echo "=========================================================="
