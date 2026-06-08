#!/usr/bin/env bash
# id: 0168-v4-on-bigdata
# description: INVESTIGATION #4 — la DATA sur v4 (test PROPRE, sans le poison v5).
# 0164 testait v5(40) sur le 4.7M (0.11, confondu). Maintenant v4(32) reset +
# train.py basse-mémoire : on distille v4 sur le master-full 4.70M (vraie data,
# 3× le 1.4M) et on benche fiable vs hc. Compare à v4/1.4M=0.72.
# + check propreté : distribution des scores du 4.7M (la val_mse 38.7 vs 36 sur
#   1.4M suggère peut-être des labels sales / captures forcées non nettoyées).
#
# Lecture : > 0.72 = plus de bonne data AIDE v4 (le vrai levier) ; < 0.72 = la
# data n'aide pas v4 (ou le 4.7M est sale → check distribution).
#
# expected_duration: ~2-3 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0168-v4-on-bigdata"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU  RAM: $(free -g 2>/dev/null | awk '/Mem/{print $2"G"}') ==="

BIG=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$BIG" ] || { echo "ABORT: master-full 4.7M (0162) absent — purgé ?"; exit 3; }
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$BIG','rb').read(8),4)[0])")
[ "$NB" -ge 3000000 ] || { echo "ABORT: dataset trop petit ($NB)"; exit 3; }
echo "master-full : $BIG ($NB records)"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== check propreté : distribution des scores du 4.7M ==="
python3 - "$BIG" <<'PYEOF'
import struct, sys, numpy as np
raw = open(sys.argv[1], 'rb').read(); n = struct.unpack_from('<I', raw, 4)[0]; REC=38
arr = np.frombuffer(raw, dtype=np.uint8, count=8+n*REC)[8:].reshape(n, REC)
sc = arr[:, 33:37].copy().view('<i4').reshape(-1).astype(np.float64)
print(f"  scores 4.7M : mean={sc.mean():.1f} std={sc.std():.1f} "
      f"min={sc.min():.0f} max={sc.max():.0f}")
for p in (1, 5, 50, 95, 99): print(f"    p{p:02d}={np.percentile(sc,p):.0f}", end="")
print()
print(f"  |score|>4900 (écrêtés/extrêmes) : {100*np.mean(np.abs(sc)>4900):.1f}%  "
      f"(1.4M propre ~symétrique ; gros déséquilibre = sale)")
PYEOF

echo; echo "=== build prod + tests (v4 32 patterns, 106 extras) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump features (106) sur le 4.7M + distill v4 (l2=1e-5) ==="
FEAT="$ART/big106.feat"; ./build-prod/jass --dump-eval-features "$BIG" "$FEAT" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$BIG" --scan-eval --eval-features-file "$FEAT" \
    --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v4big.pjtw" 2>&1 \
    | tee "$ART/train.log" | grep -E "val   :|design|split"

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
echo; echo "=== benchs fiables ==="
[ -f "$ART/v4big.pjtw" ] || { echo "ABORT: train échoué"; exit 7; }
./build-prod/jass --benchmark-scan-eval "$ART/v4big.pjtw" hc 8 12 1 0 "" 64 2>&1 | tee "$ART/vs-hc.log" | grep -E "Result|rate"
./build-prod/jass --benchmark-scan-eval "$ART/v4big.pjtw" "$V15" 9 8 1 0 "" 64 2>&1 | tee "$ART/vs-v15-d9.log" | grep -E "Result|rate"

echo; echo "=========================================================="
echo "        0168 v4 sur 4.7M (data, test propre) — VERDICT"
echo "  records : $NB"
echo "  v4/4.7M vs hc (216 fiable) : $(anyrate "$ART/vs-hc.log")"
echo "  v4/4.7M vs v15 d9 (144)    : $(anyrate "$ART/vs-v15-d9.log")"
echo "  RÉFÉRENCE v4/1.4M : vs hc 0.72  vs v15 d9 0.11"
echo "  → > 0.72 = plus de bonne data AIDE v4 (le vrai levier !)."
echo "  → ≤ 0.72 = la data n'est pas le levier sur v4 (voir distribution scores)."
echo "=========================================================="
