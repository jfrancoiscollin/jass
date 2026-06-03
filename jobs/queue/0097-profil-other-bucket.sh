#!/usr/bin/env bash
# id: 0097-profil-other-bucket
# description: Profile fine-grain du bucket "other" (40.6% au 0095).
#
# Le 0095 a montré : eval=25.7%, movegen=30.8%, apply=2.9%, other=40.6%.
# "other" est le plus gros bucket mais on ne sait pas ce qu'il contient.
# Ce job ajoute des sous-timers (accumulator / tt / zobrist) pour
# décomposer "other" en composants actionables.
#
# Buckets ajoutés (via search.cpp BD_TIME) :
#  - accumulator : push_accumulator (NNUE L1 incremental update)
#  - tt          : transposition table probe + store
#  - zobrist     : zobrist_hash computation per node
#
# Sample : 5 positions × 5000ms (identique au 0095 pour comparabilité).
# Pas de gate de qualité — c'est un job purement diagnostique.
#
# expected_duration: ~5-8 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0097-profil-other-bucket"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

V15_128_64=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw

[ -n "$V15_128_64" ] || { echo "ABORT: 128-64 weights not found"; exit 3; }
[ -f "$MASTER" ]     || { echo "ABORT: master file not found"; exit 3; }

export TMPDIR=/root/jass/tmp-build
mkdir -p "$TMPDIR"

echo "=== host ==="
echo "host: $(hostname)  nproc: $(nproc)"
g++ --version | head -1

# --- build instrumented ---
echo
echo "=== build with JASS_TIME_BREAKDOWN ==="
rm -rf build-bd
cmake -S . -B build-bd \
    -DCMAKE_BUILD_TYPE=Release \
    -DJASS_TIME_BREAKDOWN=ON \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -pipe" \
    > "$ART/cmake.log" 2>&1
if ! cmake --build build-bd -j"$(nproc)" --target jass > "$ART/build.log" 2>&1; then
    echo "BUILD FAILED. Last 40 :"; tail -40 "$ART/build.log"; exit 5
fi
echo "build OK"

# --- sample positions (RNG seed 42, identique 0091/0095) ---
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

# --- run instrumented bench ---
echo
echo "=== profile run (5 × movetime 5000ms) ==="
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

echo "raw BREAKDOWN lines :"
grep '^BREAKDOWN' "$ART/jass-stderr.log"

# --- aggregate ---
echo
python3 - <<EOF | tee "$ART/breakdown-aggregated.txt"
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
print(f"  eval         : {tot['eval']:>6}ms ({100*tot['eval']/T:>5.1f}%)")
print(f"  movegen      : {tot['movegen']:>6}ms ({100*tot['movegen']/T:>5.1f}%)")
print(f"  apply        : {tot['apply']:>6}ms ({100*tot['apply']/T:>5.1f}%)")
print(f"  accumulator  : {tot['accumulator']:>6}ms ({100*tot['accumulator']/T:>5.1f}%)  [NEW]")
print(f"  tt           : {tot['tt']:>6}ms ({100*tot['tt']/T:>5.1f}%)  [NEW]")
print(f"  zobrist      : {tot['zobrist']:>6}ms ({100*tot['zobrist']/T:>5.1f}%)  [NEW]")
print(f"  other (rest) : {other:>6}ms ({100*other/T:>5.1f}%)")
print()
print("Comparaison 0095 baseline (% du total) :")
print("  eval 25.7 → mesure cette fois")
print("  movegen 30.8 → mesure cette fois")
print("  apply 2.9 → mesure cette fois")
print("  other 40.6 → décomposé en accumulator + tt + zobrist + reste")
EOF

# --- top movers analysis ---
echo
echo "=========================================================="
echo "       0097 PROFIL OTHER BUCKET VERDICT"
echo "=========================================================="
python3 - <<EOF
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
buckets = [
    ('eval', tot['eval']),
    ('movegen', tot['movegen']),
    ('accumulator', tot['accumulator']),
    ('other-unaccounted', other),
    ('tt', tot['tt']),
    ('apply', tot['apply']),
    ('zobrist', tot['zobrist']),
]
buckets.sort(key=lambda kv: -kv[1])
print("Ranking buckets (gros au petit) :")
for name, ms in buckets:
    pct = 100*ms/T
    print(f"  {name:<20} {ms:>6}ms  ({pct:>5.1f}%)")
print()
print("Next pivot recommendation : tackler le top-3 buckets.")
EOF
