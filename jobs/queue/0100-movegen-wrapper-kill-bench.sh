#!/usr/bin/env bash
# id: 0100-movegen-wrapper-kill-bench
# description: Bench wrapper-kill movegen (track max_n incremental).
#
# Verdict 0099 : movegen 32.3% split en capture 14.3% + quiet 9.9% +
# wrapper 8.1%. Le wrapper (double scan max_n + filter dans
# generate_legal_moves) est éliminable.
#
# Optim :
#  - Add ctx.max_captures dans CaptureCtx
#  - emit_chain : drop chains < max, wipe+reset si > max, push si ==
#  - generate_captures écrit directement dans `out` (élimine la temp
#    MoveList + copy)
#  - generate_legal_moves : juste call generate_captures puis fallback
#    quiet si empty
#
# Mesures :
#  1. Breakdown : wrapper bucket doit chuter de 8.1% à ~1-2%
#  2. NPS prod vs 0091 baseline (gate >= +5%)
#  3. Bench vs Scan d10 (gate rate >= 0.85, baseline 0.870)
#
# expected_duration: ~10-15 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0100-movegen-wrapper-kill-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
SCAN_BIN=/root/jass-scan/scan_linux

[ -n "$V15_128_64" ] || { echo "ABORT: 128-64 weights"; exit 3; }
[ -f "$MASTER" ]     || { echo "ABORT: master"; exit 3; }
[ -x "$SCAN_BIN" ]   || { echo "ABORT: scan"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"

echo
echo "=== build instrumented + prod ==="
rm -rf build-bd build-prod
cmake -S . -B build-bd \
    -DCMAKE_BUILD_TYPE=Release -DJASS_TIME_BREAKDOWN=ON \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake-bd.log" 2>&1
cmake --build build-bd -j"$(nproc)" --target jass > "$ART/build-bd.log" 2>&1 || {
    echo "BUILD-BD FAIL"; tail -40 "$ART/build-bd.log"; exit 5; }
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake-prod.log" 2>&1
cmake --build build-prod -j"$(nproc)" --target jass > "$ART/build-prod.log" 2>&1 || {
    echo "BUILD-PROD FAIL"; tail -40 "$ART/build-prod.log"; exit 5; }
echo "builds OK"

# --- sample (seed 42, identique 0091-0099) ---
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

# --- 1. breakdown ---
echo
echo "=== 1) breakdown (5 × movetime 5000ms) ==="
{
    echo "hello"
    while read -r pos; do
        echo "position fen $pos"; echo "go movetime 5000"
    done < "$ART/positions.txt"
    echo "quit"
} > "$ART/hub-input.txt"
./build-bd/jass --nnue "$V15_128_64" \
    < "$ART/hub-input.txt" \
    > "$ART/jass-stdout.log" \
    2> "$ART/jass-stderr.log"
grep '^BREAKDOWN' "$ART/jass-stderr.log"

python3 - <<EOF | tee "$ART/breakdown.txt"
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
keys = ('total','eval','movegen','apply','accumulator','tt','zobrist',
        'movegen_capture','movegen_quiet')
tot = {k:0 for k in keys}
for l in lines:
    f = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in keys: tot[k] += int(f.get(f'{k}_ms', 0))
T = tot['total'] or 1
wrap = tot['movegen'] - tot['movegen_capture'] - tot['movegen_quiet']
print(f"positions: {len(lines)}  walltime: {T}ms")
print()
print(f"  eval               : {tot['eval']:>6}ms ({100*tot['eval']/T:>5.1f}%)")
print(f"  movegen TOTAL      : {tot['movegen']:>6}ms ({100*tot['movegen']/T:>5.1f}%)   [0099: 32.3%]")
print(f"    └─ capture       : {tot['movegen_capture']:>6}ms ({100*tot['movegen_capture']/T:>5.1f}%)   [0099: 14.3%]")
print(f"    └─ quiet         : {tot['movegen_quiet']:>6}ms ({100*tot['movegen_quiet']/T:>5.1f}%)   [0099:  9.9%]")
print(f"    └─ wrapper       : {wrap:>6}ms ({100*wrap/T:>5.1f}%)   [0099:  8.1% → cible <2%]")
print(f"  apply              : {tot['apply']:>6}ms ({100*tot['apply']/T:>5.1f}%)")
print(f"  accumulator        : {tot['accumulator']:>6}ms ({100*tot['accumulator']/T:>5.1f}%)")
print(f"  tt                 : {tot['tt']:>6}ms ({100*tot['tt']/T:>5.1f}%)")
EOF

# --- 2. NPS prod ---
echo
echo "=== 2) NPS PROD vs 0091 ==="
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
    p.stdin.write(f"position fen {pos}\n"); p.stdin.write("go movetime 500\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('bestmove'):
            m = re.search(r'depth=(\d+).*nodes=(\d+)', l)
            if m: depths.append(int(m.group(1))); nodes.append(int(m.group(2)))
            break
p.stdin.write("quit\n"); p.stdin.flush(); p.wait(timeout=5)
md = statistics.median(depths); mn = statistics.median(nodes)
print(f"wrapper-kill : median_depth={md}  median_nps={mn*2}")
print(f"baseline 0091 : median_depth=15  median_nps=917320")
gain = (mn*2 - 917320) / 917320 * 100
print(f"gain NPS : {gain:+.1f}%")
EOF

# --- 3. bench vs Scan d10 ---
echo
echo "=== 3) bench vs Scan d10 ==="
python3 tools/calibrate_vs_scan.py \
    --jass ./build-prod/jass --scan "$SCAN_BIN" --nnue "$V15_128_64" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log" | tail -15

echo
echo "=========================================================="
echo "       0100 MOVEGEN WRAPPER-KILL VERDICT"
echo "=========================================================="
RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')
GAIN_NPS=$(grep 'gain NPS' "$ART/nps-prod.log" | awk '{print $NF}')
WRAP_PCT=$(grep '└─ wrapper' "$ART/breakdown.txt" | grep -oE '\( *[0-9.]+%' | head -1 | tr -d '( %')
echo "Wrapper pct (était 8.1%) : $WRAP_PCT%"
echo "NPS gain vs 0091         : $GAIN_NPS"
echo "Rate vs Scan d10         : $RATE (baseline 0.870)"
echo
echo "Gates :"
echo "  Wrapper pct < 3%        : $(echo "$WRAP_PCT" | awk '{print ($1 < 3) ? "PASS" : "FAIL"}')"
echo "  NPS gain >= +5%         : $(echo "$GAIN_NPS" | tr -d '%' | awk '{print ($1 >= 5) ? "PASS" : "FAIL"}')"
echo "  Rate vs Scan d10 >= 0.85 : $(echo "$RATE" | awk '{print ($1 >= 0.85) ? "PASS" : "FAIL"}')"
echo "=========================================================="
