#!/usr/bin/env bash
# id: 0089-depth-nps-investigation
# description: Investigation — pourquoi le gap vs Scan explose en movetime.
#
# Hypothèses à départager :
#   H1: jass v11 (1024-512) NPS faible → reach less depth at 500ms
#   H2: jass search inefficient (atteint même depth mais joue mal)
#   H3: Scan time mgmt extension/réduction par coup
#   H4: SMP TT contention (séparé, déjà observé vs v8 = -0.074)
#
# Mesure :
#   * Pour 20 positions (sample du master dataset), mesure depth atteint
#     par chaque engine à movetime=500ms (et 1000ms en sanity)
#   * jass v11 1024-512 (gros modèle)
#   * jass v8 512-256 (petit modèle)
#   * Scan
#
# Output : tableau median depth + NPS par engine.
# Diagnostic :
#   - Si jass-v11 depth << jass-v8 depth → H1 (eval slow)
#   - Si jass-v8 depth << Scan depth → H2 (search ineff)
#   - Sinon → H3 (time mgmt)
#
# expected_duration: ~15-25 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0089-depth-nps-investigation"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)
[ -n "$V11" ] && [ -f "$V11" ] || { echo "ABORT: v11 not found"; exit 3; }

cmake --build build -j"$(nproc)" 2>&1 | tail -3

if ! python3 -c "import numpy" 2>/dev/null; then
    pip3 install --break-system-packages --no-cache-dir --quiet numpy
fi

python3 - <<EOF 2>&1 | tee "$ART/depth-nps-report.log"
import struct, subprocess, re, statistics, random
from pathlib import Path

MASTER = "$MASTER"
V11    = "$V11"
V8     = "$V8"
SCAN   = "$SCAN_BIN"
N_POS  = 20
MOVETIME_MS = 500

# Subsample positions
raw = Path(MASTER).read_bytes()
total = struct.unpack_from('<I', raw, 4)[0]
rng = random.Random(42)
idx = sorted(rng.sample(range(total), N_POS))

def bbs_to_fen(wm, wk, bm, bk, stm):
    parts = ['W' if stm == 0 else 'B']
    def squares(bb): return [i+1 for i in range(50) if (bb >> i) & 1]
    w_sqs = sorted(squares(wm))
    wk_sqs = sorted(squares(wk))
    b_sqs = sorted(squares(bm))
    bk_sqs = sorted(squares(bk))
    w_str = ','.join([str(s) for s in w_sqs] + [f'K{s}' for s in wk_sqs])
    b_str = ','.join([str(s) for s in b_sqs] + [f'K{s}' for s in bk_sqs])
    return f"{parts[0]}:W{w_str}:B{b_str}"

def bbs_to_scan_pos(wm, wk, bm, bk, stm):
    chars = ['e'] * 51
    chars[0] = 'B' if stm == 1 else 'W'
    for sq in range(1, 51):
        bit = 1 << (sq - 1)
        if wm & bit: chars[sq] = 'w'
        elif wk & bit: chars[sq] = 'W'
        elif bm & bit: chars[sq] = 'b'
        elif bk & bit: chars[sq] = 'B'
    return ''.join(chars)

positions = []
for i in idx:
    off = 8 + i * 38
    wm, wk, bm, bk = struct.unpack_from('<QQQQ', raw, off)
    stm = raw[off+32]
    positions.append({
        'fen':  bbs_to_fen(wm, wk, bm, bk, stm),
        'scan': bbs_to_scan_pos(wm, wk, bm, bk, stm),
    })

# === Jass measurement ===
def measure_jass(nnue_path, label):
    print(f"\n=== {label} ({nnue_path}) ===", flush=True)
    p = subprocess.Popen(['./build/jass', '--nnue', nnue_path],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    p.stdin.write("hello\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('ready'): break

    depths = []; node_counts = []; times = []
    for k, pos in enumerate(positions):
        p.stdin.write(f"position fen {pos['fen']}\n")
        p.stdin.write(f"go movetime {MOVETIME_MS}\n")
        p.stdin.flush()
        line = ""
        while True:
            l = p.stdout.readline()
            if l.startswith('bestmove'):
                line = l
                break
        m = re.search(r'depth=(\d+).*nodes=(\d+)', line)
        if m:
            d = int(m.group(1)); n = int(m.group(2))
            depths.append(d); node_counts.append(n)
            print(f"  pos {k}: depth={d} nodes={n} ({n/MOVETIME_MS*1000:.0f} nps)", flush=True)
    p.stdin.write("quit\n"); p.stdin.flush()
    p.wait(timeout=5)
    return depths, node_counts

# === Scan measurement ===
def measure_scan():
    print(f"\n=== Scan ===", flush=True)
    scan_dir = str(Path(SCAN).resolve().parent)
    p = subprocess.Popen([SCAN, "hub"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=scan_dir)
    p.stdin.write("hub\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('wait'): break
    p.stdin.write("set-param name=book value=false\n")
    p.stdin.write("init\n"); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if l.startswith('ready'): break

    depths = []; node_counts = []
    for k, pos in enumerate(positions):
        p.stdin.write("new-game\n")
        p.stdin.write(f"pos pos={pos['scan']}\n")
        p.stdin.write(f"level move-time={MOVETIME_MS/1000}\n")
        p.stdin.write("go think\n")
        p.stdin.flush()
        max_depth = 0; max_nodes = 0
        while True:
            l = p.stdout.readline().strip()
            if l.startswith('info '):
                dm = re.search(r'depth=(\d+)', l)
                nm = re.search(r'nodes=(\d+)', l)
                if dm: max_depth = max(max_depth, int(dm.group(1)))
                if nm: max_nodes = max(max_nodes, int(nm.group(1)))
            elif l.startswith('done'):
                break
        depths.append(max_depth); node_counts.append(max_nodes)
        print(f"  pos {k}: depth={max_depth} nodes={max_nodes}", flush=True)
    p.stdin.write("quit\n"); p.stdin.flush()
    try: p.wait(timeout=5)
    except: p.kill()
    return depths, node_counts

results = {}
for label, nnue in [("jass-v11 (1024-512)", V11), ("jass-v8 (512-256)", V8)]:
    if nnue:
        d, n = measure_jass(nnue, label)
        results[label] = (d, n)

d, n = measure_scan()
results["Scan"] = (d, n)

# === Summary ===
print(f"\n=========================================")
print(f"        SUMMARY (movetime={MOVETIME_MS}ms)")
print(f"=========================================")
print(f"{'engine':<25}  median_d  mean_d  median_nodes  median_nps")
for label, (depths, nodes) in results.items():
    if not depths: continue
    md = statistics.median(depths)
    avg_d = statistics.mean(depths)
    mn = statistics.median(nodes)
    nps = mn / MOVETIME_MS * 1000
    print(f"{label:<25}  {md:>8.1f}  {avg_d:>6.1f}  {mn:>12.0f}  {nps:>10.0f}")

print()
if "jass-v11 (1024-512)" in results and "jass-v8 (512-256)" in results:
    d11 = statistics.median(results["jass-v11 (1024-512)"][0])
    d8  = statistics.median(results["jass-v8 (512-256)"][0])
    print(f"v11 vs v8 depth delta : {d11 - d8:+.1f} (negative = v11 plus lent = H1 confirmé)")

if "jass-v11 (1024-512)" in results and "Scan" in results:
    d_v11 = statistics.median(results["jass-v11 (1024-512)"][0])
    d_scan = statistics.median(results["Scan"][0])
    print(f"v11 vs Scan depth delta : {d_v11 - d_scan:+.1f} (negative = Scan plus profond)")
EOF

echo
echo "=========================================================="
echo "       0089 DEPTH+NPS INVESTIGATION VERDICT"
echo "=========================================================="
echo "See $ART/depth-nps-report.log"
echo
echo "  Lecture :"
echo "    * Si v11 << v8 (depth) → eval cost dominant, optimize NNUE"
echo "    * Si v8 << Scan (depth) → search inefficient ou Scan faster"
echo "    * Si v11 ≈ v8 mais << Scan → Scan c++ tight, jass overhead Python/HUB"
echo "    * Si v11 ≈ Scan (depth) mais lose rate massif → eval quality, pas time"
echo "=========================================================="
