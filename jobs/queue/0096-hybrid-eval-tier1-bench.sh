#!/usr/bin/env bash
# id: 0096-hybrid-eval-tier1-bench
# description: Bench Tier 1 hybrid eval (cheap_eval pour RFP + NMP).
#
# Phase Hybrid Eval (post-verdict 0095) Tier 1 :
# eval_leaf (NNUE) -> eval_cheap (handcrafted) dans Reverse Futility Pruning
# et Null Move Pruning gating. Ces sites n'ont pas besoin de précision
# NNUE — un static eval ±200cp suffit pour décider de prune ou pas.
#
# Mesures :
#   1. NPS profile détaillé (5 positions × 5000ms, instrumenté breakdown)
#   2. Bench vs Scan d10 (rate qualité doit rester >= 0.80)
#   3. Bench vs v8 d10 (sanity)
#
# Gates :
#   * NPS up de >= +5% vs 0095 baseline (917K)
#   * rate vs Scan d10 >= 0.80 (perte tolérée par rapport à 0.87 baseline)
#
# expected_duration: ~10-15 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0096-hybrid-eval-tier1-bench"
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

# --- build : (a) baseline NNUE for breakdown, (b) bench build for vs-Scan ---
echo
echo "=== build INSTRUMENTED (with breakdown) ==="
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
echo "=== build PROD (no instrumentation, for bench vs Scan) ==="
cmake -S . -B build-prod \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake-prod.log" 2>&1
if ! cmake --build build-prod -j"$(nproc)" --target jass > "$ART/build-prod.log" 2>&1; then
    echo "BUILD-PROD FAILED. Last 40 :"; tail -40 "$ART/build-prod.log"; exit 5
fi
echo "build-prod OK"

# --- sample positions (same RNG as 0091/0095) ---
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

# --- 1. NPS + breakdown ---
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

echo "BREAKDOWN lines :"
grep '^BREAKDOWN' "$ART/jass-stderr.log"
echo
echo "bestmove summary :"
grep '^bestmove' "$ART/jass-stdout.log" | awk '{print $1, $2, $3, $4, $5}'

# --- aggregate ---
python3 - <<EOF | tee "$ART/breakdown-tier1.txt"
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
tot_t = tot_e = tot_m = tot_a = 0
for l in lines:
    m = re.match(r'BREAKDOWN total_ms=(\d+) eval_ms=(\d+) movegen_ms=(\d+) apply_ms=(\d+)', l)
    if not m: continue
    tot_t += int(m.group(1)); tot_e += int(m.group(2))
    tot_m += int(m.group(3)); tot_a += int(m.group(4))
tot_o = tot_t - tot_e - tot_m - tot_a
print(f"positions: {len(lines)}  total walltime: {tot_t}ms")
print(f"  eval         : {tot_e:>6}ms ({100*tot_e/tot_t:>5.1f}%)")
print(f"  movegen      : {tot_m:>6}ms ({100*tot_m/tot_t:>5.1f}%)")
print(f"  apply        : {tot_a:>6}ms ({100*tot_a/tot_t:>5.1f}%)")
print(f"  other        : {tot_o:>6}ms ({100*tot_o/tot_t:>5.1f}%)")
EOF

# --- 2. NPS direct (uninstrumented, vs 0091 apples-to-apples) ---
echo
echo "=== 2) NPS PROD (uninstrumented, vs 0091 baseline) ==="
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
print(f"v15-128-64 hybrid : median_depth={md}  median_nps={mn*2}")
print(f"  baseline 0091   : median_depth=15  median_nps=917320")
gain = (mn*2 - 917320) / 917320 * 100
print(f"  gain NPS        : {gain:+.1f}%")
EOF

# --- 3. Bench vs Scan d10 ---
echo
echo "=== 3) bench vs Scan d10 (quality regression) ==="
python3 tools/calibrate_vs_scan.py \
    --jass ./build-prod/jass --scan "$SCAN_BIN" --nnue "$V15_128_64" \
    --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-vs-scan-d10.log" | tail -20

# --- verdict ---
echo
echo "=========================================================="
echo "       0096 HYBRID EVAL TIER 1 VERDICT"
echo "=========================================================="
RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10.log" | head -1 | awk '{print $3}')
GAIN_NPS=$(grep 'gain NPS' "$ART/nps-prod.log" | awk '{print $NF}')
echo "NPS gain vs 0091 baseline : $GAIN_NPS"
echo "Rate vs Scan d10          : $RATE (baseline 0.870)"
echo
echo "Gates :"
echo "  NPS gain >= +5%        : $(echo "$GAIN_NPS" | tr -d '%' | awk '{print ($1 >= 5) ? "PASS" : "FAIL"}')"
echo "  Rate vs Scan d10 >= 0.80 : $(echo "$RATE" | awk '{print ($1 >= 0.80) ? "PASS" : "FAIL"}')"
echo "=========================================================="
