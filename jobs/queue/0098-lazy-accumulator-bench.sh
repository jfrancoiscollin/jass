#!/usr/bin/env bash
# id: 0098-lazy-accumulator-bench
# description: Bench lazy accumulator vs current main.
#
# Verdict 0097 : push_accumulator coûte 20% du temps total search. Stratégie :
# différer l'application du diff NNUE L1 jusqu'au moment où eval est
# vraiment demandée. Branches prunées avant eval (~80% des nodes en moyenne)
# n'appliquent jamais leur diff.
#
# Implémentation :
#  - push_accumulator → record (move, is_null) + clamp acc_clean_ply à ply
#  - ensure_accumulator(target) → walk acc_clean_ply jusqu'à target en
#    appliquant les pending diffs
#  - eval_leaf appelle ensure_accumulator(ply) avant access NNUE
#  - stack_pos[ply] = pos au top de negamax/quiescence (état partagé via
#    le call stack)
#
# Mesures :
#  1. NPS profile détaillé (5 positions × 5000ms, instrumenté breakdown)
#     - vérifier accumulator_pct chute de 20% à <10%
#  2. NPS prod (uninstrumented) vs 0091 baseline (917K)
#     - gate : gain >= +5%
#  3. Bench vs Scan d10 (CRITIQUE : zéro régression qualité tolérée)
#     - gate : rate >= 0.85 (baseline 0.870, tolérance -0.02)
#
# expected_duration: ~10-15 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0098-lazy-accumulator-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
SCAN_BIN=/root/jass-scan/scan_linux

[ -n "$V15_128_64" ]   || { echo "ABORT: 128-64 weights not found"; exit 3; }
[ -f "$MASTER" ]       || { echo "ABORT: master file not found"; exit 3; }
[ -x "$SCAN_BIN" ]     || { echo "ABORT: scan binary not found"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
g++ --version | head -1

# --- build instrumented + prod ---
echo
echo "=== build INSTRUMENTED ==="
rm -rf build-bd build-prod
cmake -S . -B build-bd \
    -DCMAKE_BUILD_TYPE=Release \
    -DJASS_TIME_BREAKDOWN=ON \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake-bd.log" 2>&1
if ! cmake --build build-bd -j"$(nproc)" --target jass > "$ART/build-bd.log" 2>&1; then
    echo "BUILD-BD FAILED. Last 40 :"; tail -40 "$ART/build-bd.log"; exit 5
fi
echo "build-bd OK"

echo
echo "=== build PROD ==="
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake-prod.log" 2>&1
if ! cmake --build build-prod -j"$(nproc)" --target jass > "$ART/build-prod.log" 2>&1; then
    echo "BUILD-PROD FAILED. Last 40 :"; tail -40 "$ART/build-prod.log"; exit 5
fi
echo "build-prod OK"

# --- sample positions (seed 42 identique 0091/0095/0097) ---
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

# --- 1. NPS + breakdown (vérifier accumulator chute) ---
echo
echo "=== 1) breakdown NPS profile (5 × movetime 5000ms) ==="
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

echo "raw BREAKDOWN :"
grep '^BREAKDOWN' "$ART/jass-stderr.log"

python3 - <<EOF | tee "$ART/breakdown-lazy.txt"
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
tot = {k:0 for k in ('total','eval','movegen','apply','accumulator','tt','zobrist')}
for l in lines:
    fields = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in tot:
        tot[k] += int(fields.get(f'{k}_ms', 0))
T = tot['total'] or 1
known = tot['eval'] + tot['movegen'] + tot['apply'] + tot['accumulator'] + tot['tt'] + tot['zobrist']
other = T - known
print(f"positions: {len(lines)}  total walltime: {T}ms")
print()
print(f"  eval         : {tot['eval']:>6}ms ({100*tot['eval']/T:>5.1f}%)   [vs 22.9% en 0097]")
print(f"  movegen      : {tot['movegen']:>6}ms ({100*tot['movegen']/T:>5.1f}%)   [vs 26.6% en 0097]")
print(f"  apply        : {tot['apply']:>6}ms ({100*tot['apply']/T:>5.1f}%)")
print(f"  accumulator  : {tot['accumulator']:>6}ms ({100*tot['accumulator']/T:>5.1f}%)   [vs 20.0% en 0097 — should DROP]")
print(f"  tt           : {tot['tt']:>6}ms ({100*tot['tt']/T:>5.1f}%)")
print(f"  zobrist      : {tot['zobrist']:>6}ms ({100*tot['zobrist']/T:>5.1f}%)")
print(f"  other (rest) : {other:>6}ms ({100*other/T:>5.1f}%)")
EOF

# --- 2. NPS prod ---
echo
echo "=== 2) NPS PROD (uninstrumented, vs 0091) ==="
python3 - <<EOF | tee "$ART/nps-prod.log"
import subprocess, re, statistics
from pathlib import Path
positions = Path("$ART/positions.txt").read_text().splitlines()
p = subprocess.Popen(['./build-prod/jass', '--nnue', "$V15_128_64"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write("hello\n"); p.stdin.flush()
while True:
    if p.stdout.readline().startswith('ready'): break
depths=[]; nodes=[]
for pos in positions:
    p.stdin.write(f"position fen {pos}\n")
    p.stdin.write("go movetime 500\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('bestmove'):
            m = re.search(r'depth=(\d+).*nodes=(\d+)', l)
            if m:
                depths.append(int(m.group(1))); nodes.append(int(m.group(2)))
            break
p.stdin.write("quit\n"); p.stdin.flush()
p.wait(timeout=5)
md = statistics.median(depths); mn = statistics.median(nodes)
print(f"lazy : median_depth={md}  median_nps={mn*2}")
print(f"baseline 0091 : median_depth=15  median_nps=917320")
gain = (mn*2 - 917320) / 917320 * 100
print(f"gain NPS : {gain:+.1f}%")
EOF

# --- 3. Bench vs Scan d10 (CRITIQUE) ---
echo
echo "=== 3) bench vs Scan d10 (quality regression) ==="
python3 tools/calibrate_vs_scan.py \
    --jass ./build-prod/jass --scan "$SCAN_BIN" --nnue "$V15_128_64" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log" | tail -20

# --- verdict ---
echo
echo "=========================================================="
echo "       0098 LAZY ACCUMULATOR VERDICT"
echo "=========================================================="
RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')
GAIN_NPS=$(grep 'gain NPS' "$ART/nps-prod.log" | awk '{print $NF}')
ACC_PCT=$(grep 'accumulator' "$ART/breakdown-lazy.txt" | grep -oE '\( *[0-9.]+%' | head -1 | tr -d '( %')
echo "Accumulator pct (était 20.0% en 0097) : $ACC_PCT%"
echo "NPS gain vs 0091 baseline             : $GAIN_NPS"
echo "Rate vs Scan d10                      : $RATE (baseline 0.870)"
echo
echo "Gates :"
echo "  Accumulator pct < 10%   : $(echo "$ACC_PCT" | awk '{print ($1 < 10) ? "PASS" : "FAIL"}')"
echo "  NPS gain >= +5%         : $(echo "$GAIN_NPS" | tr -d '%' | awk '{print ($1 >= 5) ? "PASS" : "FAIL"}')"
echo "  Rate vs Scan d10 >= 0.85 : $(echo "$RATE" | awk '{print ($1 >= 0.85) ? "PASS" : "FAIL"}')"
echo "=========================================================="
