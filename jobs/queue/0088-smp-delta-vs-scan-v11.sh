#!/usr/bin/env bash
# id: 0088-smp-delta-vs-scan-v11
# description: SMP delta mesuré PROPREMENT sur v11 vs Scan en movetime.
#
# 0072 testait SMP delta vs handcrafted à fixed depth → bench saturé
# (v8 atteint déjà 93-98% vs handcrafted, no headroom). delta +0.009 = noise.
# Mauvais protocole, pas mauvaise SMP.
#
# Maintenant v11 vs Scan = 0.194 (compétitif, headroom 0.50). Et movetime
# laisse SMP convertir ses cores en depth supplémentaire. Test propre :
#
#   A : v11 vs Scan threads=1 movetime=500ms × 54 games
#   B : v11 vs Scan threads=8 movetime=500ms × 54 games
#   Delta = B - A = vrai gain SMP en condition de match
#
# Si delta > 0.10 (~+70 ELO) → SMP ships default threads=8 partout.
# Si delta < 0.05 → SMP marginal sur stack jass.
#
# Bonus benchs vs v8 (peer fort) pour comparer le gain absolu :
#   * v11 vs v8 saturait à 0.639 → moins de headroom, SMP gain attendu
#     plus faible (~0.05)
#
# expected_duration: ~1-2h wall :
#   * A : 54 games × 500ms × ~120 plies ≈ 54 min nominal (mais Scan
#         + jass = 2 engines time-shared, ~108 min réel)
#   * B : pareil ~108 min
#   * Total ~3-4h
#
# Note : la mesure est lente parce que chaque game prend ~120 plies ×
# 500ms × 2 engines = ~120s par game.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0088-smp-delta-vs-scan-v11"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V11" ] && [ -f "$V11" ] || { echo "ABORT: v11 not found"; exit 3; }
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"
echo "v11 NNUE : $V11"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

# --- A : threads=1 baseline vs Scan ---
echo
echo "=========================================================="
echo "=== (A) v11 vs Scan threads=1 movetime=500ms ==="
echo "=========================================================="
START_A=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V11" \
    --movetime 0.5 --pairs 3 --jass-threads 1 \
    2>&1 | tee "$ART/A-vs-scan-t1-mt500.log"
A_SEC=$(( $(date +%s) - START_A ))
RATE_A=$(grep -oE 'score rate: [0-9.]+' "$ART/A-vs-scan-t1-mt500.log" | head -1 | awk '{print $3}')

# --- B : threads=8 SMP vs Scan ---
echo
echo "=========================================================="
echo "=== (B) v11 vs Scan threads=8 movetime=500ms ==="
echo "=========================================================="
START_B=$(date +%s)
python3 tools/calibrate_vs_scan.py \
    --jass ./build/jass --scan "$SCAN_BIN" --nnue "$V11" \
    --movetime 0.5 --pairs 3 --jass-threads 8 \
    2>&1 | tee "$ART/B-vs-scan-t8-mt500.log"
B_SEC=$(( $(date +%s) - START_B ))
RATE_B=$(grep -oE 'score rate: [0-9.]+' "$ART/B-vs-scan-t8-mt500.log" | head -1 | awk '{print $3}')

# --- Bonus : vs v8 (peer fort, headroom plus faible) ---
echo
echo "=========================================================="
echo "=== (C) v11 vs v8 threads=1 mt=500ms (peer baseline) ==="
echo "=========================================================="
START_C=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$V11" "$V8" 32 3 1 500 \
    2>&1 | tee "$ART/C-vs-v8-t1-mt500.log"
C_SEC=$(( $(date +%s) - START_C ))
RATE_C=$(grep -oE 'score rate: [0-9.]+' "$ART/C-vs-v8-t1-mt500.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "=== (D) v11 vs v8 threads=8 mt=500ms (SMP peer) ==="
echo "=========================================================="
START_D=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$V11" "$V8" 32 3 8 500 \
    2>&1 | tee "$ART/D-vs-v8-t8-mt500.log"
D_SEC=$(( $(date +%s) - START_D ))
RATE_D=$(grep -oE 'score rate: [0-9.]+' "$ART/D-vs-v8-t8-mt500.log" | head -1 | awk '{print $3}')

# ELO conversion utility
elo_from_rate() {
    python3 -c "
import math
r = max(0.001, min(0.999, $1))
print(int(round(-400 * math.log10(1.0/r - 1.0))))
"
}

ELO_A=$(elo_from_rate "$RATE_A")
ELO_B=$(elo_from_rate "$RATE_B")
DELTA_SCAN=$(python3 -c "print(round(${RATE_B}-${RATE_A}, 4))")
DELTA_ELO_SCAN=$(python3 -c "print(${ELO_B} - ${ELO_A})")

DELTA_V8=$(python3 -c "print(round(${RATE_D}-${RATE_C}, 4))")

echo
echo "=========================================================="
echo "       0088 SMP DELTA VERDICT (v11)"
echo "=========================================================="
echo "  (A) v11 vs Scan t=1 mt=500 : rate=$RATE_A  (~${ELO_A} ELO,  ${A_SEC}s)"
echo "  (B) v11 vs Scan t=8 mt=500 : rate=$RATE_B  (~${ELO_B} ELO,  ${B_SEC}s)"
echo "       SMP delta vs Scan : $DELTA_SCAN  (~${DELTA_ELO_SCAN} ELO)"
echo
echo "  (C) v11 vs v8 t=1 mt=500   : rate=$RATE_C  (${C_SEC}s)"
echo "  (D) v11 vs v8 t=8 mt=500   : rate=$RATE_D  (${D_SEC}s)"
echo "       SMP delta vs v8 : $DELTA_V8"
echo
echo "  Reference :"
echo "    v11 vs Scan fixed-depth d10 (0083) : 0.194"
echo "    v11 vs v8 fixed-depth d10  (0083) : 0.639"
echo
echo "  Decision :"
echo "    * delta vs Scan > 0.10 (~+70 ELO) → SMP ships default threads=8 partout"
echo "    * delta ∈ [0.05, 0.10] → SMP utile, opt-in pour matches sérieux"
echo "    * delta < 0.05 → SMP marginal, TT contention sur notre stack"
echo "=========================================================="
