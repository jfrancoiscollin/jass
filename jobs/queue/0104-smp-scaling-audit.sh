#!/usr/bin/env bash
# id: 0104-smp-scaling-audit
# description: Audit du scaling SMP (lazy threads) post-0103.
#
# Tous les benchs précédents (0091 → 0103) ont mesuré NPS à threads=1.
# Le code SMP existe (helpers font iterative deepening avec TT partagée)
# mais on ne sait pas si le scaling effectif est positif au-delà de 1.
#
# Hypothèses à tester :
#  - NPS scaling > 1 à 2 threads ? (idéal : ~1.5-1.8×)
#  - NPS scaling > 1 à 4 threads ? (idéal : ~2.5-3×)
#  - NPS scaling > 1 à 8 threads ? (souvent dégradation à >4 par
#    contention TT en lazy SMP non-distribué)
#
# Mesures :
#  1. NPS prod à threads ∈ {1, 2, 4, 8} : 5 positions × 5000ms each
#  2. Rate vs Scan d10 à threads=4 : ELO scaling vs threads=1 baseline
#
# Pas de gate strict — purement diagnostique. Si scaling > 1.5× à 4
# threads ET rate vs Scan ne baisse pas, recommandation = utiliser
# threads=N en production.
#
# expected_duration: ~15-20 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0104-smp-scaling-audit"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
SCAN_BIN=/root/jass-scan/scan_linux

[ -n "$V15_128_64" ] || { echo "ABORT: weights"; exit 3; }
[ -f "$MASTER" ]     || { echo "ABORT: master"; exit 3; }
[ -x "$SCAN_BIN" ]   || { echo "ABORT: scan"; exit 3; }

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

# sample positions (seed 42, same as 0091-0103)
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

# Helper: run NPS bench at given threads count
nps_for_threads() {
    local nthreads=$1
    python3 - "$nthreads" "$V15_128_64" "$ART/positions.txt" <<'EOF'
import subprocess, re, sys, statistics
from pathlib import Path
nthreads = int(sys.argv[1])
nnue_path = sys.argv[2]
positions_file = sys.argv[3]
positions = Path(positions_file).read_text().splitlines()
p = subprocess.Popen(['./build-prod/jass', '--nnue', nnue_path],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write("hello\n"); p.stdin.flush()
while True:
    if p.stdout.readline().startswith('ready'): break
p.stdin.write(f"setoption name threads value {nthreads}\n"); p.stdin.flush()
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
if not nodes:
    print(f"threads={nthreads}  ERROR_no_nodes")
    sys.exit(1)
md = statistics.median(depths); mn = statistics.median(nodes)
# NPS = nodes / time. Time = 5000ms. NPS = nodes * 1000 / 5000 = nodes / 5
nps = int(mn / 5)
print(f"threads={nthreads}  median_depth={md}  median_nodes={mn}  median_nps={nps}")
EOF
}

# 1. NPS scaling at threads ∈ {1, 2, 4, 8}
echo
echo "=== 1) NPS scaling at threads ∈ {1, 2, 4, 8} ==="
THREADS_LIST=(1 2 4 8)
RESULTS_FILE="$ART/nps-by-threads.log"
> "$RESULTS_FILE"
for t in "${THREADS_LIST[@]}"; do
    [ "$t" -le "$NCPU" ] || { echo "skip threads=$t (>$NCPU cpu)"; continue; }
    echo "  measuring threads=$t..."
    nps_for_threads "$t" | tee -a "$RESULTS_FILE"
done

# Compute scaling factors
python3 - <<EOF | tee "$ART/scaling-summary.txt"
import re
from pathlib import Path
lines = Path("$RESULTS_FILE").read_text().splitlines()
data = {}
for l in lines:
    m = re.search(r'threads=(\d+)\s+median_depth=(\d+)\s+median_nodes=(\d+)\s+median_nps=(\d+)', l)
    if m:
        data[int(m.group(1))] = {
            'depth': int(m.group(2)),
            'nodes': int(m.group(3)),
            'nps': int(m.group(4)),
        }
print()
print("Scaling table :")
print(f"  {'threads':<10} {'depth':<8} {'nps':<14} {'scale vs 1t':<12}")
base_nps = data.get(1, {}).get('nps', 0)
for t in sorted(data.keys()):
    nps = data[t]['nps']
    depth = data[t]['depth']
    scale = nps / base_nps if base_nps else 0.0
    eff = scale / t * 100 if base_nps else 0.0
    print(f"  {t:<10} {depth:<8} {nps:<14} {scale:>5.2f}× ({eff:>4.0f}%)")
EOF

# 2. Bench vs Scan at threads=4
echo
echo "=== 2) Bench vs Scan d10 à threads=4 ==="
# calibrate_vs_scan.py supports --threads? check signature
python3 tools/calibrate_vs_scan.py --help 2>&1 | grep -i thread | head -3
# If --threads exists, use it; otherwise document this in artefacts
if python3 tools/calibrate_vs_scan.py --help 2>&1 | grep -q -- '--threads'; then
    echo "  (running with threads=4)"
    python3 tools/calibrate_vs_scan.py \
        --jass ./build-prod/jass --scan "$SCAN_BIN" --nnue "$V15_128_64" \
        --depth 10 --pairs 3 --threads 4 \
        2>&1 | tee "$ART/bench-vs-scan-d10-4t.log" | tail -15
else
    echo "  --threads non supporté par calibrate_vs_scan.py, skip"
fi

# verdict
echo
echo "=========================================================="
echo "       0104 SMP SCALING AUDIT VERDICT"
echo "=========================================================="
cat "$ART/scaling-summary.txt"
echo
RATE4T=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-vs-scan-d10-4t.log" 2>/dev/null | head -1 | awk '{print $3}')
if [ -n "$RATE4T" ]; then
    echo "Rate vs Scan d10 à threads=4 : $RATE4T (baseline threads=1 : 0.870)"
else
    echo "Rate vs Scan d10 à threads=4 : non mesuré"
fi
echo
echo "Recommandation :"
python3 - <<EOF
import re
from pathlib import Path
lines = Path("$RESULTS_FILE").read_text().splitlines()
data = {}
for l in lines:
    m = re.search(r'threads=(\d+).*median_nps=(\d+)', l)
    if m: data[int(m.group(1))] = int(m.group(2))
base = data.get(1, 0)
if base == 0:
    print("  Pas de baseline 1t mesurée — résultats inutilisables.")
elif 4 in data:
    scale4 = data[4] / base
    if scale4 >= 2.5:
        print(f"  Scaling 4t excellent ({scale4:.2f}×). Recommander threads=4 en prod.")
    elif scale4 >= 1.5:
        print(f"  Scaling 4t modéré ({scale4:.2f}×). Recommander threads=4 si pas de contention TT visible.")
    else:
        print(f"  Scaling 4t FAIBLE ({scale4:.2f}×). Lazy SMP peu efficace ; investiguer TT layout / locks.")
EOF
echo "=========================================================="
