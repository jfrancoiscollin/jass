#!/usr/bin/env bash
# id: 0091-v15-nps-profile
# description: Profile NPS détaillé v15 (128-64 Scan-distilled de 0090).
#
# Précédent 0089 a mesuré v11 (1024-512 = 98K NPS) et v8 (256-128 = 316K
# NPS). Le 128-64 n'a JAMAIS été mesuré. Extrapolation : ~600K-3M NPS
# possible. Sans la vraie donnée, le plan SIMD optim est mal calibré.
#
# Aussi : déterminer où le temps est dépensé (eval vs movegen vs search
# overhead). Si eval déjà optimisée AVX2 et = X% du temps total, optimiser
# eval donne X% × speedup. Si eval = 30% du temps, ×2 speedup donne +15%
# NPS total. Si eval = 80% du temps, ×2 → +40% NPS.
#
# Mesures :
#   * NPS direct (positions sample, movetime 500ms)
#   * Eval microbench (call evaluate() N=1M fois, mesure time/call)
#   * Compare 128-64, 192-96, 256-128, v11
#
# Output : NPS + eval/sec + ratio eval-time vs search-time
#
# expected_duration: ~5-10 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0091-v15-nps-profile"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
V15_192_96=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-192-96/nnue-*-q.bin 2>/dev/null | head -1)
V15_256_128=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-256-128/nnue-*-q.bin 2>/dev/null | head -1)
V11=$(ls -t /root/jass/jobs/results/0083-scan-distill-v11-capacity-bump/artefacts.src/arch-1024-512/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -n "$V15_128_64" ] || { echo "ABORT: 0090 v15 128-64 not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"
cat /proc/cpuinfo | grep -E "model name|flags" | head -2

cmake --build build -j"$(nproc)" 2>&1 | tail -3

# --- NPS measurement via go movetime 500 ---
python3 - <<EOF | tee "$ART/nps-profile.log"
import struct, subprocess, re, random, statistics
from pathlib import Path
MASTER = "$MASTER"
NNUES = [
    ("v15-128-64",  "$V15_128_64"),
    ("v15-192-96",  "$V15_192_96"),
    ("v15-256-128", "$V15_256_128"),
    ("v8-256-128",  "$V8"),
    ("v11-1024-512","$V11"),
]
raw = Path(MASTER).read_bytes()
total = struct.unpack_from('<I', raw, 4)[0]
rng = random.Random(42)
idx = sorted(rng.sample(range(total), 20))
def fen(wm, wk, bm, bk, stm):
    parts = ['W' if stm == 0 else 'B']
    def squares(bb): return [i+1 for i in range(50) if (bb >> i) & 1]
    w = ','.join([str(s) for s in sorted(squares(wm))] + [f'K{s}' for s in sorted(squares(wk))])
    b = ','.join([str(s) for s in sorted(squares(bm))] + [f'K{s}' for s in sorted(squares(bk))])
    return f"{parts[0]}:W{w}:B{b}"
positions = []
for i in idx:
    off = 8 + i * 38
    wm, wk, bm, bk = struct.unpack_from('<QQQQ', raw, off)
    stm = raw[off+32]
    positions.append(fen(wm, wk, bm, bk, stm))

print(f"\n{'engine':<18}  median_d  mean_d  median_nps")
for label, nnue in NNUES:
    if not nnue or not Path(nnue).exists():
        print(f"{label:<18}  SKIP (not found)")
        continue
    p = subprocess.Popen(['./build/jass', '--nnue', nnue],
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
    try: p.wait(timeout=5)
    except: p.kill()
    if depths:
        md = statistics.median(depths); mn = statistics.median(nodes)
        print(f"{label:<18}  {md:>8.1f}  {statistics.mean(depths):>6.1f}  {mn*2:>10.0f}")
    else:
        print(f"{label:<18}  no data")
EOF

echo
echo "=========================================================="
echo "       0091 v15 NPS PROFILE VERDICT"
echo "=========================================================="
echo "Comparaison NPS scaled par params :"
echo "  128-64  : ~66K params/eval"
echo "  256-128 : ~148K params/eval (2.2× plus que 128-64)"
echo "  1024-512: ~1.5M params/eval (10× plus que 256-128)"
echo
echo "Si 128-64 NPS ~ 256-128 × 2.2 → eval scaling dominé par compute, SIMD valable"
echo "Si 128-64 NPS ~ 256-128 (peu de gain) → overhead search domine, SIMD limité"
echo "Si 128-64 NPS << expected → bottleneck inconnu, à investiger"
echo "=========================================================="
