#!/usr/bin/env bash
# id: 0092-perf-profile-hot-path
# description: Profile callgraph hot-path v15 128-64 — où part le temps ?
#
# 0091 a révélé : 128-64 = 917K NPS, et le ratio NPS(128-64) / NPS(256-128)
# = 1.43× alors que les params sont 2.2× moins. Donc eval N'EST PAS le
# bottleneck unique. Search/movegen/overhead pèsent significativement.
#
# Conséquence : un 4× SIMD AVX2 sur eval ne donnera PAS 4× NPS total.
# Si eval = X% du temps, gain max = 1 / (1 - X(1 - 1/4)).
#
# But : mesurer la breakdown réelle eval vs movegen vs search overhead
# pour calibrer Phase A++. Sans cette donnée le plan SIMD est aveugle.
#
# Méthode :
#   1. Build avec -fno-omit-frame-pointer pour callgraphs propres
#   2. perf record -F 999 --call-graph fp sur go movetime 5000 ×5 positions
#   3. perf report --stdio agrégé par symbole
#   4. Classification heuristique : eval / movegen / search / other
#
# expected_duration: ~3-5 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0092-perf-profile-hot-path"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -n "$V15_128_64" ] || { echo "ABORT: 128-64 weights not found"; exit 3; }

echo "=== host + perf availability ==="
echo "host: $(hostname)  nproc: $(nproc)"
which perf || { echo "ABORT: perf not installed"; exit 4; }
cat /proc/sys/kernel/perf_event_paranoid

# --- build with frame pointers ---
echo
echo "=== rebuild with -fno-omit-frame-pointer ==="
cmake -S . -B build-perf \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -fno-omit-frame-pointer -g" \
    2>&1 | tail -3
cmake --build build-perf -j"$(nproc)" --target jass 2>&1 | tail -3

# --- extract 5 sample positions ---
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

# --- run search under perf record ---
echo
echo "=== perf record (5 positions × movetime 5000ms = 25s) ==="

INPUT_FILE="$ART/hub-input.txt"
{
    echo "hello"
    while read -r pos; do
        echo "position fen $pos"
        echo "go movetime 5000"
    done < "$ART/positions.txt"
    echo "quit"
} > "$INPUT_FILE"

perf record -F 999 --call-graph fp -o "$ART/perf.data" -- \
    ./build-perf/jass --nnue "$V15_128_64" < "$INPUT_FILE" \
    > "$ART/jass-stdout.log" 2>&1

echo "perf.data size : $(du -h "$ART/perf.data" | cut -f1)"

# --- aggregate report ---
echo
echo "=== perf report (flat, top 30 symbols) ==="
perf report -i "$ART/perf.data" --stdio --no-children --percent-limit 0.5 \
    2>/dev/null | tee "$ART/perf-flat.txt" | head -60

echo
echo "=== perf report (callgraph, top 20 with children) ==="
perf report -i "$ART/perf.data" --stdio --percent-limit 1.0 -g graph,0.5,caller \
    2>/dev/null | tee "$ART/perf-callgraph.txt" | head -100

# --- classification heuristique ---
echo
echo "=========================================================="
echo "       0092 HOT PATH CLASSIFICATION"
echo "=========================================================="
python3 - <<EOF
import re, subprocess
out = subprocess.check_output(['perf', 'report', '-i', '$ART/perf.data',
                                '--stdio', '--no-children', '--percent-limit', '0.1'],
                               stderr=subprocess.DEVNULL, text=True)
# parse lines: pct symbol
buckets = {'eval/nnue': 0.0, 'movegen': 0.0, 'search': 0.0,
           'apply_move': 0.0, 'other': 0.0}
EVAL_KW = ['nnue', 'evaluate', 'feature', 'halfmen', 'mlpnetwork',
           'dot_uint8', 'matmul', 'accumulat']
MOVEGEN_KW = ['movegen', 'generate_move', 'gen_captures', 'gen_quiet']
SEARCH_KW = ['search', 'alphabet', 'negamax', 'order_move', 'see_',
             'killer', 'history', 'lmr', 'tt_probe']
APPLY_KW = ['apply_move', 'undo_move', 'do_move']
total_pct = 0.0
for line in out.splitlines():
    m = re.match(r'\s+(\d+\.\d+)%\s+\S+\s+\S+\s+\[\.\]\s+(.+)$', line)
    if not m: continue
    pct = float(m.group(1)); sym = m.group(2).lower()
    total_pct += pct
    if any(k in sym for k in EVAL_KW):     buckets['eval/nnue']  += pct
    elif any(k in sym for k in MOVEGEN_KW): buckets['movegen']    += pct
    elif any(k in sym for k in APPLY_KW):   buckets['apply_move'] += pct
    elif any(k in sym for k in SEARCH_KW):  buckets['search']     += pct
    else:                                   buckets['other']      += pct
print(f"Total accounted : {total_pct:.1f}%")
print(f"  eval/nnue   : {buckets['eval/nnue']:>5.1f}%")
print(f"  movegen     : {buckets['movegen']:>5.1f}%")
print(f"  apply_move  : {buckets['apply_move']:>5.1f}%")
print(f"  search core : {buckets['search']:>5.1f}%")
print(f"  other       : {buckets['other']:>5.1f}%")
print()
e = buckets['eval/nnue']
if e > 0:
    print(f"Eval = {e:.0f}% du temps total.")
    print(f"  Si SIMD donne 4× speedup eval, gain NPS total = {100 / (100 - e * 0.75):.2f}×")
    print(f"  Pour atteindre 8.1M NPS (Scan parity) depuis 917K : besoin {8100/917:.1f}× total")
EOF
echo "=========================================================="
