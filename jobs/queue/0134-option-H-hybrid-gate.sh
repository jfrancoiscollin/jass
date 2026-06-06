#!/usr/bin/env bash
# id: 0134-option-H-hybrid-gate
# description: Phase 0 — quick-win gate d'Option H (NNUE hybride avec
# squelette handcrafted). On entraîne DEUX 128-64 sur EXACTEMENT les
# mêmes labels Scan-d10 (réutilise 0131), la seule différence étant la
# target :
#   - vanilla  : target = scan_d10                       (éval absolue)
#   - residual : target = scan_d10 - handcrafted         (Option H §H)
#                joué à l'inférence comme handcrafted + residual_nnue
# Puis bench A/B : hybrid(residual) vs vanilla, à profondeur fixe.
#
# Gate : si rate(hybrid vs vanilla) >= 0.53 (~+20 ELO) → le squelette
# handcrafted aide → investir dans le downsize d'archi (64-32 / 48-24,
# forward 2-3× plus rapide = gain time-search). Sinon → drop Option H.
#
# expected_duration: ~40-70 min wall (2 trainings 128-64 sur 1.5M +
# 1 rewrite handcrafted + 2 quantize + 2 benchs d10).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0134-option-H-hybrid-gate"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

echo "=== host : $(hostname)  nproc=$NCPU ==="

# --- Réutilise artefacts 0131 (labels Scan d10) + v15 -----------------------
DATA_SCAN=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/master-1500K-scan-d10.jnnw
[ -f "$DATA_SCAN" ] || { echo "ABORT: 0131 scan-d10 labels manquants ($DATA_SCAN)"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights manquants"; exit 3; }
echo "labels  : $DATA_SCAN"
echo "v15     : $V15"

echo
echo "=== Phase 0 : scipy/numpy/torch ==="
python3 -c "import numpy, torch" 2>/dev/null || {
    PIP_SCRATCH=/root/jass/.pip-scratch; mkdir -p "$PIP_SCRATCH"
    for a in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages --no-cache-dir --quiet \
            numpy torch && break; sleep 5
    done; rm -rf "$PIP_SCRATCH"; }

echo
echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

echo
echo "=== Phase 2 : squelette handcrafted aligné sur les positions Scan-d10 ==="
SKEL="$ART/master-1500K-handcrafted.jnnw"
./build-prod/jass --rewrite-scores-with-handcrafted "$DATA_SCAN" "$SKEL" \
    > "$ART/handcrafted-rewrite.log" 2>&1
[ -f "$SKEL" ] || { echo "ABORT: handcrafted rewrite"; tail "$ART/handcrafted-rewrite.log"; exit 4; }

train_one () {  # $1=tag  shift -> extra train_v3 args
    local tag="$1"; shift
    local d="$ART/$tag"; mkdir -p "$d"
    echo "  --- train $tag ---"
    python3 tools/train_v3.py \
        --data     "$DATA_SCAN" \
        --archs    128-64 \
        --encoding halfmen \
        --epochs   30 \
        --batch    512 \
        --out-dir  "$d" \
        "$@" 2>&1 | tee "$d/train.log"
    python3 tools/quantize_mlp.py \
        --in  "$d/nnue-128-64.bin" \
        --data "$DATA_SCAN" \
        --out "$d/nnue-128-64-q.bin" 2>&1 | tee "$d/quantize.log"
}

echo
echo "=== Phase 3a : train VANILLA (target = scan) ==="
train_one vanilla
echo
echo "=== Phase 3b : train RESIDUAL (target = scan - handcrafted, lambda=1.0) ==="
train_one residual --skeleton-data "$SKEL" --lambda 1.0

VANILLA_Q="$ART/vanilla/nnue-128-64-q.bin"
RESID_Q="$ART/residual/nnue-128-64-q.bin"
[ -f "$VANILLA_Q" ] && [ -f "$RESID_Q" ] || { echo "ABORT: quantize manquant"; exit 4; }

echo
echo "=== Phase 4a : GATE — hybrid(residual) vs vanilla (d10, 54 games) ==="
./build-prod/jass --benchmark-nnue-hybrid "$RESID_Q" "$VANILLA_Q" 10 3 1 0 \
    2>&1 | tee "$ART/gate-hybrid-vs-vanilla.log"
RATE_GATE=$(grep -oE 'HYBRID score rate vs vanilla: [0-9.]+' "$ART/gate-hybrid-vs-vanilla.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=== Phase 4b : sanity — vanilla (notre retrain) vs v15 (contrôle data/pipeline) ==="
./build-prod/jass --benchmark-nnue-vs-nnue "$VANILLA_Q" "$V15" 10 3 1 0 \
    2>&1 | tee "$ART/sanity-vanilla-vs-v15.log"
RATE_SANITY=$(grep -oE 'A score rate: [0-9.]+' "$ART/sanity-vanilla-vs-v15.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=========================================================="
echo "        0134 OPTION H — HYBRID GATE VERDICT"
echo "=========================================================="
echo "  hybrid(residual) vs vanilla : rate ${RATE_GATE:-n/a}   (le GATE)"
echo "  vanilla(retrain) vs v15     : rate ${RATE_SANITY:-n/a} (contrôle ~0.5 attendu)"
python3 - "${RATE_GATE:-}" <<'EOF'
import sys, math
r = sys.argv[1]
try: r = float(r)
except:
    print("  → pas de rate parsé, voir gate-hybrid-vs-vanilla.log"); raise SystemExit
elo = -400*math.log10(1/r-1) if 0<r<1 else (float('inf') if r>=1 else -float('inf'))
print(f"  → ΔELO hybrid vs vanilla ≈ {elo:+.0f}")
if r >= 0.55:
    print("  → OPTION H PASS net — squelette handcrafted aide clairement.")
    print("    Next : Phase 2, downsize 64-32 / 48-24 hybride (forward 2-3× plus vite).")
elif r >= 0.53:
    print("  → OPTION H signal faible mais positif (>~+20 ELO). Tenter le downsize.")
else:
    print("  → OPTION H FLAT — le résidu n'aide pas à archi égale. Drop, pivot (F/B).")
EOF
echo "=========================================================="
