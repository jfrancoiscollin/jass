#!/usr/bin/env bash
# id: 0105-smp-selfplay
# description: Self-play Jass-1t vs Jass-4t à movetime fixe pour valider
# le gain ELO du SMP (vraie métrique, contrairement à NPS main thread).
#
# 0104bis a montré : helpers SMP donnent +2 depth gratis à 4 threads
# (NPS main thread baisse, mais depth atteinte monte). Le bench à depth
# fixe vs Scan ne pouvait pas exposer ce gain (depth contraint = pas de
# bénéfice).
#
# 0105 mesure le vrai impact : self-play à movetime fixe.
#   - Engine A : threads=1 (baseline)
#   - Engine B : threads=4 (smp)
#   - movetime = 3000ms (suffisamment long pour que depth gain compte)
#   - même weights, même opening pool
#   - 4 paires × N openings × 2 colours
#
# Verdict :
#   - rate_B > 0.55 (CI exclusive de 0.5) → recommander threads=4 prod
#   - rate_B ≈ 0.50 → SMP neutre ELO (depth gain insuffisant ou TT
#     contention compense)
#   - rate_B < 0.45 → régression (bug ou contention extrême)
#
# Test secondaire : 1t vs 2t (cheap CPU, voir si 2t suffit)
#
# expected_duration: ~10-15 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0105-smp-selfplay"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15_128_64" ] || { echo "ABORT: weights"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
NCPU=$(nproc)

echo
echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

# Args: --benchmark-nnue-vs-nnue <a.bin> <b.bin> [depth] [pairs] [t_a] [movetime] [t_b]
# A = baseline 1t, B = smp Nt
run_match() {
    local label="$1"
    local t_a="$2"
    local t_b="$3"
    local pairs="$4"
    local movetime="$5"
    local log="$ART/match-${label}.log"
    echo
    echo "=== match $label : A=${t_a}t vs B=${t_b}t, pairs=$pairs, movetime=${movetime}ms ==="
    ./build-prod/jass --benchmark-nnue-vs-nnue \
        "$V15_128_64" "$V15_128_64" \
        64 "$pairs" "$t_a" "$movetime" "$t_b" \
        2>&1 | tee "$log" | tail -8
}

# 1t vs 4t, movetime 3000ms, 4 pairs (≈ 8 × 12 openings = 96 games)
run_match "1t-vs-4t" 1 4 4 3000

# 1t vs 2t, mêmes openings, 4 pairs
run_match "1t-vs-2t" 1 2 4 3000

# 1t vs 1t (sanity : doit donner ≈ 0.50)
run_match "1t-vs-1t-sanity" 1 1 2 3000

echo
echo "=========================================================="
echo "       0105 SMP SELF-PLAY VERDICT"
echo "=========================================================="
python3 - <<'EOF'
import re
from pathlib import Path
ART = Path("/root/jass/jobs/results/0105-smp-selfplay/artefacts.src")
for name in ["1t-vs-4t", "1t-vs-2t", "1t-vs-1t-sanity"]:
    log = (ART / f"match-{name}.log").read_text()
    m_res = re.search(r'Result: A=(\d+) B=(\d+) Draws=(\d+) \(total (\d+)\)', log)
    if not m_res:
        print(f"  {name}: PARSE FAIL")
        continue
    a, b, d, tot = map(int, m_res.groups())
    rate_a = (a + 0.5 * d) / tot
    rate_b = (b + 0.5 * d) / tot
    # Wilson 95% CI half-width
    import math
    p = rate_b; n = tot
    z = 1.96
    half = z * math.sqrt(p*(1-p)/n) if n > 0 else 0
    elo_b = -400 * math.log10(1/rate_b - 1) if 0 < rate_b < 1 else float('inf')
    print(f"  {name:<20} A={a:>3} B={b:>3} D={d:>3}  rate_B={rate_b:.3f} ±{half:.3f}  ΔELO≈{elo_b:+.0f}")

# Decision for 4t
log4 = (ART / "match-1t-vs-4t.log").read_text()
m = re.search(r'Result: A=(\d+) B=(\d+) Draws=(\d+) \(total (\d+)\)', log4)
if m:
    a, b, d, tot = map(int, m.groups())
    rate = (b + 0.5 * d) / tot
    import math
    half = 1.96 * math.sqrt(rate*(1-rate)/tot)
    lo = rate - half
    print()
    if lo > 0.50:
        print(f"  → 4t GAIN ELO confirmé (rate {rate:.3f}, lo {lo:.3f}). Recommander threads=4 prod.")
    elif rate > 0.50:
        print(f"  → 4t suggère gain mais CI inclut 0.50 (rate {rate:.3f} ±{half:.3f}). Inconclusive, augmenter pairs.")
    else:
        print(f"  → 4t NEUTRE ou régression (rate {rate:.3f}). SMP n'aide pas au-delà du depth gain visible.")
EOF
echo "=========================================================="
