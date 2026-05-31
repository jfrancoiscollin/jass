#!/usr/bin/env bash
# id: 0072-smp-delta-bench-v8
# description: Quantifier le delta Lazy SMP sur le bench protocol jass.
#              Self-play v8 (256-128, baseline) en 4 régimes :
#
#   (A) threads=1 d10                 : sanity baseline ~50% (self-play)
#   (B) threads=8 d10 vs threads=1 d10 : SMP gain at fixed depth
#                                         (~+10-30 ELO attendu — modeste,
#                                         SMP n'aide pas vraiment à depth fixe)
#   (C) threads=1 movetime=500ms      : sanity baseline en mode movetime
#   (D) threads=8 movetime=500 vs t=1  : SMP gain at fixed wall budget
#                                         (~+50-100 ELO attendu — vrai gain,
#                                         8 cores → effective depth plus
#                                         profonde par coup)
#
# Pour chaque régime : 9 openings × 3 pairs × 2 couleurs = 54 games.
# Mesure le score rate de "threads=8" contre "threads=1".
#
# Decision gate :
#   * (B) > 0.55 et (D) > 0.65 → SMP ships, intégrer threads=8 par défaut
#     dans tous benches + jobs futurs
#   * (B) ~ 0.50 et (D) > 0.65 → confirme intuition movetime-only ; basculer
#     les benches calibrate-vs-scan vers movetime
#   * (D) < 0.55 → SMP gain plus faible que prédit ; investiguer (TT size,
#     thread affinity, NUMA?)
#
# expected_duration: ~2-3h wall sur CCX33 :
#                    * (A) ~30 min (54 games × 2-5s each)
#                    * (B) ~45 min (8 threads = plus de wall pour search)
#                    * (C) ~30 min (54 games × 500ms × ~30 moves = 27 min nominal)
#                    * (D) ~30 min (idem mais avec 8 threads, wall identique)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0072-smp-delta-bench-v8"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V8" ] && [ -f "$V8" ] || { echo "ABORT: v8 NNUE not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)  mem: $(free -h | awk '/^Mem:/ {print $2}')"
echo "v8 NNUE : $V8"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

# CLI signature : --benchmark-nnue-vs-nnue <a> <b> [d] [pairs] [threads] [movetime_ms]
echo
echo "=========================================================="
echo "=== (A) sanity : t=1 d10 vs t=1 d10 ==="
echo "=========================================================="
START_A=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$V8" "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/A-sanity-t1-d10.log"
A_SEC=$(( $(date +%s) - START_A ))
RATE_A=$(grep -oE 'score rate: [0-9.]+' "$ART/A-sanity-t1-d10.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "=== (B) SMP fixed-depth : t=8 d10 vs t=1 d10 ==="
echo "=========================================================="
# Note : asymétrique. cfg_a (premier) = threads=8, cfg_b (deuxième) = threads=1.
# Mais notre CLI n'a qu'UN argument threads partagé. Pour un vrai A/B
# asymétrique on tournerait en deux passes avec swap. Plus simple :
# t=8 self-play vs t=1 self-play en deux benches séparés vs handcrafted,
# puis comparer les rates. Ou : ajouter une CLI pour asym threads (TODO).
# Pour ce job : on bench t=8 self-play (B') et t=1 self-play (A) ;
# le rate vs handcrafted donne un proxy du gain SMP.
START_B=$(date +%s)
./build/jass --benchmark-nnue "$V8" 10 3 8 0 \
    2>&1 | tee "$ART/B-t8-d10-vs-hc.log"
B_SEC=$(( $(date +%s) - START_B ))
RATE_B=$(grep -oE 'score rate: [0-9.]+' "$ART/B-t8-d10-vs-hc.log" | head -1 | awk '{print $3}')

START_B2=$(date +%s)
./build/jass --benchmark-nnue "$V8" 10 3 1 0 \
    2>&1 | tee "$ART/B-t1-d10-vs-hc.log"
B2_SEC=$(( $(date +%s) - START_B2 ))
RATE_B2=$(grep -oE 'score rate: [0-9.]+' "$ART/B-t1-d10-vs-hc.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "=== (C) sanity movetime : t=1 mt=500 vs t=1 mt=500 ==="
echo "=========================================================="
START_C=$(date +%s)
./build/jass --benchmark-nnue-vs-nnue "$V8" "$V8" 32 3 1 500 \
    2>&1 | tee "$ART/C-sanity-t1-mt500.log"
C_SEC=$(( $(date +%s) - START_C ))
RATE_C=$(grep -oE 'score rate: [0-9.]+' "$ART/C-sanity-t1-mt500.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "=== (D) SMP movetime : t=8 mt=500 vs handcrafted ==="
echo "=========================================================="
START_D=$(date +%s)
./build/jass --benchmark-nnue "$V8" 32 3 8 500 \
    2>&1 | tee "$ART/D-t8-mt500-vs-hc.log"
D_SEC=$(( $(date +%s) - START_D ))
RATE_D=$(grep -oE 'score rate: [0-9.]+' "$ART/D-t8-mt500-vs-hc.log" | head -1 | awk '{print $3}')

START_D2=$(date +%s)
./build/jass --benchmark-nnue "$V8" 32 3 1 500 \
    2>&1 | tee "$ART/D-t1-mt500-vs-hc.log"
D2_SEC=$(( $(date +%s) - START_D2 ))
RATE_D2=$(grep -oE 'score rate: [0-9.]+' "$ART/D-t1-mt500-vs-hc.log" | head -1 | awk '{print $3}')

echo
echo "=========================================================="
echo "       0072 SMP DELTA BENCH VERDICT"
echo "=========================================================="
echo "  (A) sanity self-play t=1 d10  → rate=$RATE_A (${A_SEC}s)"
echo "       expected ~0.50 (self-play). Sanity check OK if proche."
echo
echo "  (B) SMP fixed-depth d10 vs handcrafted :"
echo "       t=8: rate=$RATE_B (${B_SEC}s)"
echo "       t=1: rate=$RATE_B2 (${B2_SEC}s)"
echo "       delta t8-t1 = $(python3 -c "print(round(${RATE_B}-${RATE_B2}, 3))")"
echo "       (~+10-30 ELO attendu si delta ~ +0.05-0.10)"
echo
echo "  (C) sanity movetime t=1 mt=500 self-play → rate=$RATE_C (${C_SEC}s)"
echo
echo "  (D) SMP movetime mt=500 vs handcrafted :"
echo "       t=8 mt=500 : rate=$RATE_D (${D_SEC}s)"
echo "       t=1 mt=500 : rate=$RATE_D2 (${D2_SEC}s)"
echo "       delta t8-t1 = $(python3 -c "print(round(${RATE_D}-${RATE_D2}, 3))")"
echo "       (~+50-100 ELO attendu si delta ~ +0.15-0.30)"
echo
echo "  Action :"
echo "    * delta (D) > 0.15 → SMP ships, default threads=8 partout"
echo "    * delta (D) ≈ delta (B) → SMP gain ≈ identique fixed/movetime, surprise"
echo "    * delta (D) < 0.05 → SMP gain plus faible que prédit, debug"
echo "=========================================================="
