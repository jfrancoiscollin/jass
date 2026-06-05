#!/usr/bin/env bash
# id: 0125-movegen-king-ray-bench
# description: Bench NPS du king ray-mask precomputed (PR #189 prochaine).
# Cible : +2-4% NPS sur quiet bucket via élimination des neighbour() calls
# en inner loop des king moves (quiet + captures).
#
# Compare vs baseline 0103 (NPS 1.29M).
#
# expected_duration: ~10 min
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0125-movegen-king-ray-bench"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

TMPDIR_REAL=/root/jass/.compile-tmp
mkdir -p "$TMPDIR_REAL"
export TMPDIR="$TMPDIR_REAL"

echo "=== Phase 1 : build prod (king ray table active) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$(nproc)" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] || { echo "ABORT: v15 weights missing"; exit 3; }

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master missing"; exit 3; }

echo
echo "=== Phase 2 : NPS bench (5 positions × 5s, median) ==="
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

python3 - <<EOF > "$ART/nps.log"
import subprocess, re, statistics
from pathlib import Path
positions = Path("$ART/positions.txt").read_text().splitlines()
p = subprocess.Popen(['./build-prod/jass', '--nnue', "$V15"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write("hello\n"); p.stdin.flush()
while not p.stdout.readline().startswith('ready'): pass
depths=[]; nodes=[]
for pos in positions:
    p.stdin.write(f"position fen {pos}\n")
    p.stdin.write("go movetime 5000\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if not l: break
        if l.startswith('bestmove'):
            m = re.search(r'depth=(\d+).*nodes=(\d+)', l)
            if m:
                depths.append(int(m.group(1))); nodes.append(int(m.group(2)))
            break
p.stdin.write("quit\n"); p.stdin.flush()
p.wait(timeout=10)
md = statistics.median(depths); mn = statistics.median(nodes)
nps = int(mn / 5)
print(f"median_depth={md}  median_nodes={mn}  median_nps={nps}")
EOF
cat "$ART/nps.log"

NPS=$(grep -oE 'median_nps=[0-9]+' "$ART/nps.log" | cut -d= -f2)

echo
echo "=== Phase 3 : rate vs Scan d10 (correctness gate) ==="
SCAN_BIN=/root/jass-scan/scan_linux
if [ -x "$SCAN_BIN" ]; then
    python3 tools/calibrate_vs_scan.py \
        --jass ./build-prod/jass --scan "$SCAN_BIN" --nnue "$V15" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-vs-scan.log" | tail -5
    RATE=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan.log" | head -1 | awk '{print $3}')
else
    echo "  scan binary missing — skip rate bench"
    RATE="n/a"
fi

echo
echo "=========================================================="
echo "       0125 KING RAY MASKS BENCH VERDICT"
echo "=========================================================="
echo "  NPS         : $NPS  (baseline 0103 : 1.29M)"
echo "  Rate Scan d10 : $RATE (baseline : 0.870)"
echo
if [ -n "$NPS" ]; then
    python3 - <<EOF
nps = $NPS
baseline = 1290000
gain = (nps - baseline) / baseline * 100
print(f"  NPS gain vs 0103 : {gain:+.1f}%")
if gain >= 3:
    print(f"  → PASS : king ray masks contribuent au NPS.")
elif gain >= 0:
    print(f"  → marginal ({gain:+.1f}%) ; au moins pas de régression.")
else:
    print(f"  → régression {gain:.1f}%, investiguer.")
EOF
fi
echo "=========================================================="
