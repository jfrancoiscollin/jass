#!/usr/bin/env bash
# id: 0105bis-smp-selfplay-smaller
# description: Self-play SMP 1t vs 4t, sizing réaliste (0105 sous-dimensionné).
#
# 0105 : pairs=4, movetime=3000 → 96 games × ~3 min = ~5h par match.
# 0105bis : pairs=1, movetime=1500ms → 24 games × ~1 min = ~25 min par
# match. 3 matches → ~75 min total. Acceptable.
#
# Trade-off : moins de games = plus de variance. Mais 24 games suffit
# pour distinguer rate=0.50 de rate=0.65 avec p<0.10 (Wilson half-width
# ~0.18 sur n=24). Pour des effets plus subtils (rate=0.55), c'est
# inconcluant — auquel cas on resize encore en haut.
#
# expected_duration: ~75 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0105bis-smp-selfplay-smaller"
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

# Args: --benchmark-nnue-vs-nnue <a> <b> <depth> <pairs> <t_a> <movetime> <t_b>
run_match() {
    local label="$1"; local t_a="$2"; local t_b="$3"
    local pairs="$4"; local movetime="$5"
    local log="$ART/match-${label}.log"
    echo
    echo "=== match $label : A=${t_a}t vs B=${t_b}t, pairs=$pairs, movetime=${movetime}ms ==="
    # stdbuf -oL pour line-buffer stdout, sinon rien ne s'affiche avant la fin
    stdbuf -oL ./build-prod/jass --benchmark-nnue-vs-nnue \
        "$V15_128_64" "$V15_128_64" \
        64 "$pairs" "$t_a" "$movetime" "$t_b" \
        2>&1 | stdbuf -oL tee "$log" | tail -8
}

# pairs=1, movetime=1500ms : 24 games × ~1 min each = ~25 min per match
run_match "1t-vs-4t" 1 4 1 1500
run_match "1t-vs-2t" 1 2 1 1500
run_match "1t-vs-1t-sanity" 1 1 1 1500

echo
echo "=========================================================="
echo "       0105bis SMP SELF-PLAY VERDICT"
echo "=========================================================="
python3 - <<'EOF'
import re, math
from pathlib import Path
ART = Path("/root/jass/jobs/results/0105bis-smp-selfplay-smaller/artefacts.src")
results = {}
for name in ["1t-vs-4t", "1t-vs-2t", "1t-vs-1t-sanity"]:
    log_path = ART / f"match-{name}.log"
    if not log_path.exists():
        print(f"  {name}: MISSING"); continue
    log = log_path.read_text()
    m_res = re.search(r'Result: A=(\d+) B=(\d+) Draws=(\d+) \(total (\d+)\)', log)
    if not m_res:
        print(f"  {name}: PARSE FAIL"); continue
    a, b, d, tot = map(int, m_res.groups())
    rate_b = (b + 0.5 * d) / tot
    half = 1.96 * math.sqrt(rate_b*(1-rate_b)/tot) if tot > 0 else 0
    elo_b = -400 * math.log10(1/rate_b - 1) if 0 < rate_b < 1 else (float('inf') if rate_b == 1 else -float('inf'))
    results[name] = (rate_b, half, elo_b, tot)
    print(f"  {name:<20} A={a:>3} B={b:>3} D={d:>3} (n={tot})  rate_B={rate_b:.3f} ±{half:.3f}  ΔELO≈{elo_b:+.0f}")

if "1t-vs-4t" in results:
    rate, half, elo, n = results["1t-vs-4t"]
    lo = rate - half
    print()
    if lo > 0.50:
        print(f"  → 4t GAIN ELO confirmé (CI inférieure {lo:.3f}). Recommander threads=4 prod.")
    elif rate > 0.55:
        print(f"  → 4t suggère gain (rate {rate:.3f}) mais CI inclut 0.50 sur n={n}. Probable signal, refaire avec n×2 si critique.")
    elif rate >= 0.45:
        print(f"  → 4t NEUTRE (rate {rate:.3f}). SMP gain depth compensé par TT contention.")
    else:
        print(f"  → 4t RÉGRESSION (rate {rate:.3f}). Bug ou contention extrême.")
EOF
echo "=========================================================="
