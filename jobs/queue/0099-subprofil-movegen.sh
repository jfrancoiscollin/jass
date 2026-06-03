#!/usr/bin/env bash
# id: 0099-subprofil-movegen
# description: Sub-profile du bucket movegen (26.6% au 0097).
#
# Verdict 0097 : movegen = 26.6% du total, plus gros bucket actionable
# (eval = 22.9%, accumulator = 20% mais lazy a échoué). Avant de tenter
# une optim coûteuse (magic bitboards, lookup tables, SIMD), il faut
# savoir QUEL sous-composant domine :
#   - generate_captures (multi-capture sequence enumeration, récursive)
#   - generate_quiet_moves (simples moves, bitboard shifts)
#
# Ce job ajoute 2 sub-buckets BD_TIME dans movegen.cpp :
#   - movegen_capture : generate_captures total (= scan + multi-capture rec)
#   - movegen_quiet   : generate_quiet_moves
# La différence movegen - capture - quiet = overhead wrapper (filter
# max-captures, push_back).
#
# Sample : 5 positions × 5000ms (identique seed 42 que 0091/0095/0097).
# Pas de gate qualité — job purement diagnostique.
#
# expected_duration: ~5-8 min wall
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0099-subprofil-movegen"
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

# --- sample positions ---
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

# --- profile run ---
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
keys = ('total','eval','movegen','apply','accumulator','tt','zobrist',
        'movegen_capture','movegen_quiet')
tot = {k:0 for k in keys}
for l in lines:
    fields = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in keys:
        tot[k] += int(fields.get(f'{k}_ms', 0))
T = tot['total'] or 1
mg_wrapper = tot['movegen'] - tot['movegen_capture'] - tot['movegen_quiet']
known = (tot['eval'] + tot['movegen'] + tot['apply']
         + tot['accumulator'] + tot['tt'] + tot['zobrist'])
other = T - known
print(f"positions: {len(lines)}  total walltime: {T}ms")
print()
print(f"  eval               : {tot['eval']:>6}ms ({100*tot['eval']/T:>5.1f}%)")
print(f"  movegen TOTAL      : {tot['movegen']:>6}ms ({100*tot['movegen']/T:>5.1f}%)")
print(f"    └─ capture       : {tot['movegen_capture']:>6}ms ({100*tot['movegen_capture']/T:>5.1f}%)  [NEW]")
print(f"    └─ quiet         : {tot['movegen_quiet']:>6}ms ({100*tot['movegen_quiet']/T:>5.1f}%)  [NEW]")
print(f"    └─ wrapper       : {mg_wrapper:>6}ms ({100*mg_wrapper/T:>5.1f}%)  [filter max-captures + push]")
print(f"  apply              : {tot['apply']:>6}ms ({100*tot['apply']/T:>5.1f}%)")
print(f"  accumulator        : {tot['accumulator']:>6}ms ({100*tot['accumulator']/T:>5.1f}%)")
print(f"  tt                 : {tot['tt']:>6}ms ({100*tot['tt']/T:>5.1f}%)")
print(f"  zobrist            : {tot['zobrist']:>6}ms ({100*tot['zobrist']/T:>5.1f}%)")
print(f"  other (rest)       : {other:>6}ms ({100*other/T:>5.1f}%)")
EOF

# --- ranking + reco ---
echo
echo "=========================================================="
echo "       0099 SUB-PROFIL MOVEGEN VERDICT"
echo "=========================================================="
python3 - <<EOF
import re
from pathlib import Path
lines = [l for l in Path("$ART/jass-stderr.log").read_text().splitlines()
         if l.startswith('BREAKDOWN')]
keys = ('total','eval','movegen','apply','accumulator','tt','zobrist',
        'movegen_capture','movegen_quiet')
tot = {k:0 for k in keys}
for l in lines:
    fields = dict(p.split('=') for p in l.split()[1:] if '=' in p)
    for k in keys:
        tot[k] += int(fields.get(f'{k}_ms', 0))
T = tot['total'] or 1
mg_capture_pct = 100*tot['movegen_capture']/T
mg_quiet_pct = 100*tot['movegen_quiet']/T
print(f"Movegen 26.6% (0097) se décompose en :")
print(f"  capture : {mg_capture_pct:.1f}% du total search")
print(f"  quiet   : {mg_quiet_pct:.1f}% du total search")
print()
if mg_capture_pct > mg_quiet_pct * 1.5:
    print("→ CAPTURE est le hot path. Optim cible :")
    print("  - Pre-filter : skip generate_captures si pas d'opponent en attack range")
    print("  - Lookup tables des squares atteignables par capture")
    print("  - Optim extend_man_captures / extend_king_captures (récursion)")
elif mg_quiet_pct > mg_capture_pct * 1.5:
    print("→ QUIET est le hot path. Optim cible :")
    print("  - SIMD bitboard shifts pour génération masse")
    print("  - PEXT/PDEP pour iteration des moves possibles")
else:
    print("→ Capture et quiet sont équilibrés. Optimiser les deux.")
    print("  Commencer par capture (souvent plus de gain potentiel).")
EOF
