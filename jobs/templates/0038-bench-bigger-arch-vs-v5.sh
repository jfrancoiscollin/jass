#!/usr/bin/env bash
# id: 0038-bench-bigger-arch-vs-v5
# description: Head-to-head des bigger archs (entraînées en 0037 sur le
#              MÊME corpus que 0018) vs v5 (256-128 de 0018). Variable
#              unique: la taille du réseau.
#
#              Tests chaque arch >256-128 dans l'ordre de val MSE:
#                * 512-256 vs v5
#                * 1024-512 vs v5
#                * 2048-1024 vs v5
#
#              Décision globale:
#                * Si une arch bigger gagne +50+ ELO vs v5 → adopter
#                  comme nouveau default (et la re-bencher contre
#                  Cycle 9 si on a tourné 0034-0036).
#                * Si toutes plafonnent dans [-15, +15 ELO] vs v5 →
#                  archi n'est pas le bottleneck; chercher ailleurs
#                  (loss, encoding, data quality).
#                * Si toutes régressent (<-30 ELO) → overfitting sur
#                  1M, ou hyper-params inadaptés à la taille.
# expected_duration: ~3 × 45 min sur 4 vCPU CCX23 (3 archs benchés au
#                    depth 6 + depth 10).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0038-bench-bigger-arch-vs-v5"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V5=$(ls -t /root/jass/jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V5" ] && [ -f "$V5" ] || { echo "ABORT: v5 NNUE not found"; exit 3; }

BIG_DIR="/root/jass/jobs/results/0037-train-bigger-arch-on-existing-1M/artefacts.src"
[ -d "$BIG_DIR" ] || { echo "ABORT: 0037 not done yet"; exit 3; }

cmake --build build -j"$(nproc)" 2>&1 | tail -3

declare -A RATES_D10
for arch in 512-256 1024-512 2048-1024; do
    BIG="$BIG_DIR/nnue-${arch}-q.bin"
    if [ ! -f "$BIG" ]; then
        echo "  skip $arch — not built by 0037"
        continue
    fi
    echo "=== bench $arch vs v5 (256-128), depth 10, 3 pairs ==="
    ./build/jass --benchmark-nnue-vs-nnue "$BIG" "$V5" 10 3 \
        2>&1 | tee "$ART/bench-${arch}-d10.log"
    RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-${arch}-d10.log" | head -1 | awk '{print $3}')
    RATES_D10[$arch]=$RATE
done

echo
echo "=========================================================="
echo "       0038 BIGGER ARCH vs V5 VERDICT"
echo "=========================================================="
echo "  (depth 10, 3 pairs, score rate from bigger-arch's POV)"
for arch in 512-256 1024-512 2048-1024; do
    r=${RATES_D10[$arch]:-N/A}
    echo "  $arch:  $r"
done
echo
echo "  Reading: rate >0.55 → solid gain over v5 (256-128)."
echo "  Reading: rate ≈0.50 → archi n'est pas le bottleneck."
echo "  Reading: rate <0.45 → bigger overfits sur 1M; il faut plus de data."
echo "=========================================================="
