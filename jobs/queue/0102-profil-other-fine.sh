#!/usr/bin/env bash
# id: 0102-profil-other-fine
# description: Sub-profil fin du bucket "other" (était 17.4% en 0097,
# ~20% post-0101 baseline accélérée).
#
# Verdict 0101 : capture pre-filter livré +29.7% NPS. Reste comme plus
# gros bucket inconnu : "other-unaccounted" (estimé 18-20%).
#
# Suspects principaux dans negamax inner loop :
#  - move ordering : score+sort O(n²) sur ~30 moves par node
#  - 3-fold repetition : hash_path linear scan + push/pop
#  - history/killer updates : sur cutoff
#  - alpha-beta / LMR / LMP overhead branches
#
# Ce job ajoute 2 sub-buckets :
#  - move_ordering : BD_TIME dans order_moves
#  - path_check    : BD_TIME dans path_contains + push/pop
#
# Sample : 5 positions × 5000ms (identique seed 42).
# Pas de gate qualité — purement diagnostique.
#
# expected_duration: ~5-8 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0102-profil-other-fine"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -n "$V15_128_64" ] || { echo "ABORT: weights"; exit 3; }
[ -f "$MASTER" ]     || { echo "ABORT: master"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"

echo
echo "=== build with JASS_TIME_BREAKDOWN ==="
rm -rf build-bd
cmake -S . -B build-bd \
    -DCMAKE_BUILD_TYPE=Release -DJASS_TIME_BREAKDOWN=ON \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
cmake --build build-bd -j"$(nproc)" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -40 "$ART/build.log"; exit 5; }

# sample positions
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

# profile run
echo
echo "=== profile run (5 × movetime 5000ms) ==="
{
    echo "hello"
    while read -r pos; do echo "position fen $pos"; echo "go movetime 5000"; done < "$ART/positions.txt"
    echo "quit"
} > "$ART/hub-input.txt"
./build-bd/jass --nnue "$V15_128_64" < "$ART/hub-input.txt" \
    > "$ART/jass-stdout.log" 2> "$ART/jass-stderr.log"

grep '^BREAKDOWN' "$ART/jass-stderr.log"

python3 - <<EOF | tee "$ART/breakdown-aggregated.txt"
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
keys = ('total','eval','movegen','apply','accumulator','tt','zobrist',
        'movegen_capture','movegen_quiet','move_ordering','path_check')
tot = {k:0 for k in keys}
for l in lines:
    f = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in keys: tot[k] += int(f.get(f'{k}_ms', 0))
T = tot['total'] or 1
known = (tot['eval'] + tot['movegen'] + tot['apply']
         + tot['accumulator'] + tot['tt'] + tot['zobrist']
         + tot['move_ordering'] + tot['path_check'])
other = T - known
print(f"positions: {len(lines)}  walltime: {T}ms")
print()
print(f"  eval            : {tot['eval']:>6}ms ({100*tot['eval']/T:>5.1f}%)")
print(f"  movegen TOTAL   : {tot['movegen']:>6}ms ({100*tot['movegen']/T:>5.1f}%)")
print(f"    └─ capture    : {tot['movegen_capture']:>6}ms ({100*tot['movegen_capture']/T:>5.1f}%)")
print(f"    └─ quiet      : {tot['movegen_quiet']:>6}ms ({100*tot['movegen_quiet']/T:>5.1f}%)")
print(f"  apply           : {tot['apply']:>6}ms ({100*tot['apply']/T:>5.1f}%)")
print(f"  accumulator     : {tot['accumulator']:>6}ms ({100*tot['accumulator']/T:>5.1f}%)")
print(f"  tt              : {tot['tt']:>6}ms ({100*tot['tt']/T:>5.1f}%)")
print(f"  zobrist         : {tot['zobrist']:>6}ms ({100*tot['zobrist']/T:>5.1f}%)")
print(f"  move_ordering   : {tot['move_ordering']:>6}ms ({100*tot['move_ordering']/T:>5.1f}%)  [NEW]")
print(f"  path_check      : {tot['path_check']:>6}ms ({100*tot['path_check']/T:>5.1f}%)  [NEW]")
print(f"  other-rest      : {other:>6}ms ({100*other/T:>5.1f}%)")
EOF

echo
echo "=========================================================="
echo "       0102 OTHER-UNACCOUNTED SUB-PROFIL VERDICT"
echo "=========================================================="
python3 - <<EOF
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
keys = ('total','eval','movegen','apply','accumulator','tt','zobrist',
        'movegen_capture','movegen_quiet','move_ordering','path_check')
tot = {k:0 for k in keys}
for l in lines:
    f = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in keys: tot[k] += int(f.get(f'{k}_ms', 0))
T = tot['total'] or 1
mo = 100 * tot['move_ordering'] / T
pc = 100 * tot['path_check'] / T
known = (tot['eval'] + tot['movegen'] + tot['apply']
         + tot['accumulator'] + tot['tt'] + tot['zobrist']
         + tot['move_ordering'] + tot['path_check'])
other = 100 * (T - known) / T
print(f"NEW sub-buckets pct du total :")
print(f"  move_ordering : {mo:.1f}%")
print(f"  path_check    : {pc:.1f}%")
print(f"  other-rest    : {other:.1f}%")
print()
biggest = max(('move_ordering', mo), ('path_check', pc), ('other-rest', other),
              key=lambda kv: kv[1])
print(f"→ Plus gros sous-bucket dans 'other' : {biggest[0]} ({biggest[1]:.1f}%)")
if biggest[0] == 'move_ordering':
    print("  Optim possible : sort O(n²) → O(n log n), ou MVV/LVA scoring inline")
elif biggest[0] == 'path_check':
    print("  Optim possible : remplacer vector linear scan par hashset (3-fold)")
else:
    print("  Optim possible : sub-profil supplémentaire (alpha-beta logic, LMR/LMP)")
EOF
