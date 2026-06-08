#!/usr/bin/env bash
# id: 0169-data-cleanliness-diag
# description: INVESTIGATION #5 — POURQUOI le 4.7M fait chuter v4 (0.72→0.42) ?
# 0168 : distribution des scores 4.7M asymétrique (p99=+9989 vs p01=-1060).
# MAIS relabel_with_scan drop déjà les captures forcées (défaut), et 0162 a
# utilisé les MÊMES args que 0141. Donc l'asymétrie vient d'ailleurs.
#
# 1) DIAGNOSTIC : comparer les distributions 1.4M (propre, 0.72) vs 4.7M côte à
#    côte. Le 1.4M est-il symétrique (→ le 4.7M est anormal) ou aussi asymétrique
#    (→ l'asymétrie n'est pas la cause) ?
# 2) TEST : v4 distillé sur le 4.7M FILTRÉ (|score|≤4900, queue extrême retirée).
#    > 0.72 = la queue extrême était le poison → plus de data propre aide.
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0169-data-cleanliness-diag"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

SMALL=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
BIG=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$SMALL" ] || { echo "ABORT: 1.4M (0141) absent"; exit 3; }
[ -f "$BIG" ]   || { echo "ABORT: 4.7M (0162) absent"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== 1) DIAGNOSTIC : distributions 1.4M vs 4.7M côte à côte ==="
python3 - "$SMALL" "$BIG" <<'PYEOF'
import struct, sys, numpy as np
def dist(path):
    raw=open(path,'rb').read(); n=struct.unpack_from('<I',raw,4)[0]; REC=38
    a=np.frombuffer(raw,dtype=np.uint8,count=8+n*REC)[8:].reshape(n,REC)
    return a[:,33:37].copy().view('<i4').reshape(-1).astype(np.float64), n
for tag,p in (("1.4M propre",sys.argv[1]),("4.7M full",sys.argv[2])):
    sc,n=dist(p)
    pct={q:np.percentile(sc,q) for q in (1,5,25,50,75,95,99)}
    print(f"  {tag} (n={n}): mean={sc.mean():+.0f} std={sc.std():.0f}  "
          f"p01={pct[1]:+.0f} p25={pct[25]:+.0f} p50={pct[50]:+.0f} p75={pct[75]:+.0f} p99={pct[99]:+.0f}")
    print(f"      |score|>4900 : {100*np.mean(np.abs(sc)>4900):.1f}%   "
          f"asymétrie(p99+p01)={pct[99]+pct[1]:+.0f} (0=symétrique)")
PYEOF

echo; echo "=== 2) FILTRER le 4.7M (|score|≤4900) → 4.7M-filtré ==="
FILT="$ART/big-filtered.jnnw"
python3 - "$BIG" "$FILT" <<'PYEOF'
import struct, sys, numpy as np
raw=open(sys.argv[1],'rb').read(); n=struct.unpack_from('<I',raw,4)[0]; REC=38
a=np.frombuffer(raw,dtype=np.uint8,count=8+n*REC)[8:].reshape(n,REC)
sc=a[:,33:37].copy().view('<i4').reshape(-1)
keep=np.abs(sc)<=4900
out=a[keep]
with open(sys.argv[2],'wb') as f:
    f.write(b'JNNW'); f.write(struct.pack('<I',int(out.shape[0]))); f.write(out.tobytes())
print(f"  gardé {out.shape[0]}/{n} ({100*out.shape[0]/n:.1f}%) ; retiré {n-out.shape[0]} extrêmes")
PYEOF
NBF=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$FILT','rb').read(8),4)[0])")

echo; echo "=== build prod + tests (v4) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== distill v4 sur 4.7M-filtré (l2=1e-5) ==="
FEAT="$ART/filt106.feat"; ./build-prod/jass --dump-eval-features "$FILT" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$FILT" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v4f.pjtw" 2>&1 \
    | tee "$ART/train.log" | grep -E "val   :|design|split"
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
[ -f "$ART/v4f.pjtw" ] && ./build-prod/jass --benchmark-scan-eval "$ART/v4f.pjtw" hc 8 12 1 0 "" 64 2>&1 | tee "$ART/vs-hc.log" | grep -E "Result|rate"

echo; echo "=========================================================="
echo "        0169 DATA — DIAGNOSTIC + 4.7M FILTRÉ — VERDICT"
echo "  4.7M-filtré : $NBF records"
echo "  v4/4.7M-filtré vs hc (216) : $(anyrate "$ART/vs-hc.log")"
echo "  réf : v4/1.4M=0.72  v4/4.7M-brut=0.42"
echo "  → > 0.72 = la queue extrême était le poison (data propre aide)."
echo "  → ≈0.42 = le filtre ne suffit pas (relabel full-pool buggé, ou data ≠ levier)."
echo "  (comparer les distributions ci-dessus : 1.4M symétrique vs 4.7M ?)"
echo "=========================================================="
