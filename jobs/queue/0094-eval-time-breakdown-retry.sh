#!/usr/bin/env bash
# id: 0094-eval-time-breakdown-retry
# description: Retry 0093 with proper build-error reporting (no tail -3
#              swallowing the gcc output) + macro fix (unique BD_TIME var
#              names via __COUNTER__).
#
# 0093 a failed silencieusement : `cmake --build ... | tail -3` a masqué
# l'erreur de compile. Hypothèse : -Wshadow + variable __bd___LINE__
# dupliquée par token-paste cassé. Corrigé via BD_TIME_CAT + __COUNTER__.
#
# expected_duration: ~5-8 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0094-eval-time-breakdown-retry"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -n "$V15_128_64" ]   || { echo "ABORT: 128-64 weights not found"; exit 3; }
[ -f "$MASTER" ]       || { echo "ABORT: master file not found"; exit 3; }

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
g++ --version | head -1

# --- build with time-breakdown, FULL output captured ---
echo
echo "=== rebuild with -DJASS_TIME_BREAKDOWN=ON (full log) ==="
cmake -S . -B build-bd \
    -DCMAKE_BUILD_TYPE=Release \
    -DJASS_TIME_BREAKDOWN=ON \
    > "$ART/cmake-configure.log" 2>&1
echo "configure rc=$?"

# Don't pipe through tail -- capture full log + check rc explicitly.
if ! cmake --build build-bd -j"$(nproc)" --target jass \
        > "$ART/cmake-build.log" 2>&1; then
    echo "BUILD FAILED. Last 40 lines :"
    tail -40 "$ART/cmake-build.log"
    exit 5
fi
echo "build OK : $(ls -l build-bd/jass | awk '{print $5}') bytes"

# --- extract 5 sample positions (same RNG as 0091) ---
python3 - <<EOF > "$ART/positions.txt"
import struct, random
from pathlib import Path
raw = Path("$MASTER").read_bytes()
total = struct.unpack_from('<I', raw, 4)[0]
rng = random.Random(42)
idx = sorted(rng.sample(range(total), 5))
def fen(wm, wk, bm, bk, stm):
    def sq(bb): return [i+1 for i in range(50) if (bb >> i) & 1]
    w = ','.join([str(s) for s in sorted(sq(wm))] + [f'K{s}' for s in sorted(sq(wk))])
    b = ','.join([str(s) for s in sorted(sq(bm))] + [f'K{s}' for s in sorted(sq(bk))])
    return f"{'W' if stm==0 else 'B'}:W{w}:B{b}"
for i in idx:
    off = 8 + i * 38
    wm, wk, bm, bk = struct.unpack_from('<QQQQ', raw, off)
    stm = raw[off+32]
    print(fen(wm, wk, bm, bk, stm))
EOF
echo "sample positions :"
cat "$ART/positions.txt"

# --- run 5 × movetime 5000ms ---
echo
echo "=== 5 × go movetime 5000ms ==="

INPUT_FILE="$ART/hub-input.txt"
{
    echo "hello"
    while read -r pos; do
        echo "position fen $pos"
        echo "go movetime 5000"
    done < "$ART/positions.txt"
    echo "quit"
} > "$INPUT_FILE"

./build-bd/jass --nnue "$V15_128_64" \
    < "$INPUT_FILE" \
    > "$ART/jass-stdout.log" \
    2> "$ART/jass-stderr.log"

echo "stdout :"
cat "$ART/jass-stdout.log"
echo
echo "BREAKDOWN lines :"
grep '^BREAKDOWN' "$ART/jass-stderr.log" || echo "(none — instrumentation didn't fire)"

# --- aggregate ---
echo
echo "=========================================================="
echo "       0094 EVAL / MOVEGEN / APPLY / OTHER BREAKDOWN"
echo "=========================================================="
python3 - <<EOF
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
if not lines:
    print("no BREAKDOWN lines — abort")
    raise SystemExit(0)
tot_t = tot_e = tot_m = tot_a = 0
for l in lines:
    m = re.match(r'BREAKDOWN total_ms=(\d+) eval_ms=(\d+) movegen_ms=(\d+) apply_ms=(\d+)', l)
    if not m: continue
    tot_t += int(m.group(1))
    tot_e += int(m.group(2))
    tot_m += int(m.group(3))
    tot_a += int(m.group(4))
tot_o = tot_t - tot_e - tot_m - tot_a
print(f"positions : {len(lines)}")
print(f"total walltime : {tot_t}ms")
print()
print(f"  eval         : {tot_e:>6}ms ({100*tot_e/tot_t:>5.1f}%)")
print(f"  movegen      : {tot_m:>6}ms ({100*tot_m/tot_t:>5.1f}%)")
print(f"  apply (pos)  : {tot_a:>6}ms ({100*tot_a/tot_t:>5.1f}%)")
print(f"  other        : {tot_o:>6}ms ({100*tot_o/tot_t:>5.1f}%)")
print()
e_frac = tot_e / tot_t
g4   = 1.0 / (1.0 - 0.75  * e_frac)
g8   = 1.0 / (1.0 - 0.875 * e_frac)
ginf = 1.0 / (1.0 - e_frac)
print("Amdahl — gain NPS total via SIMD eval :")
print(f"  ×4  SIMD : {g4:.2f}×  (917K → {int(917*g4)}K NPS)")
print(f"  ×8  SIMD : {g8:.2f}×  (917K → {int(917*g8)}K NPS)")
print(f"  ×∞  SIMD : {ginf:.2f}× (917K → {int(917*ginf)}K NPS, upper bound)")
print()
need_total = 8100 / 917
print(f"Cible Scan parity = 8.1M NPS → besoin {need_total:.1f}× total")
if ginf >= need_total:
    print(f"  -> faisable même avec eval seul (gain max = {ginf:.1f}×)")
else:
    print(f"  -> NON faisable via eval seul. Il faut AUSSI optimiser non-eval ({(1-e_frac)*100:.0f}% du temps).")
EOF
echo "=========================================================="
