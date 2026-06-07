#!/usr/bin/env bash
# id: 0161-redistill-on-4p5M
# description: AXE QUALITÉ — re-distillation sur le dataset ÉLARGI (~4.5M, 0160).
# 0155 a montré v5 (40 pat + 112 extras) sur 1.4M = 0.25 vs hc (sur-sparsité).
# Même config, mais sur ~4.5M : la sparsité se résorbe-t-elle ? ATTRIBUTION du
# DATA : 0161(4.5M) vs 0155(1.4M), config identique.
#
# Baselines : v4(32,1.4M)=0.75 ; v5(40,1.4M)=0.44 ; v5+ext(40,112,1.4M)=0.25.
# Lecture : remonte vers/au-dessus de 0.75 = plus de data débloque la richesse.
#
# expected_duration: ~2-3.5 h (4.5M = ~3× le fit de 1.4M).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0161-redistill-on-4p5M"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

BIG=/root/jass/jobs/results/0160-gen-more-data-3M/artefacts.src/master-clean-scan-d10-4p5M.jnnw
# garde-fou : 0160 doit avoir produit un dataset conséquent (>3M records)
if [ ! -f "$BIG" ]; then echo "ABORT: dataset 4.5M (0160) absent — 0160 a-t-il réussi ?"; exit 3; fi
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$BIG','rb').read(8),4)[0])" 2>/dev/null || echo 0)
[ "$NB" -ge 3000000 ] || { echo "ABORT: dataset trop petit ($NB records)"; exit 3; }
echo "dataset élargi : $BIG ($NB records)"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests (v5 40 pat + 112 extras + accumulateur) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== dump-eval-features (112) sur le dataset 4.5M ==="
FEAT="$ART/big112.feat"
./build-prod/jass --dump-eval-features "$BIG" "$FEAT" 2>&1 | tail -1

probe () { python3 - "$1" <<'PYEOF'
import struct,numpy as np,sys
raw=open(sys.argv[1],'rb').read();_,_,s,np_,ne=struct.unpack_from('<IIIII',raw,0)
pm=np.frombuffer(raw,'<i4',np_,20).astype(np.float64)
print(f"    n_pat={np_} PAT nnz={(pm!=0).sum()}/{np_} ({100*(pm!=0).sum()/np_:.1f}%)  (v5/1.4M était 3.6%)")
PYEOF
}
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }

train_one () {
    echo; echo "=== TRAIN $1 (v5+112 sur 4.5M, material-anchor 1.0, l2=$2) ==="
    python3 pattern_jass/tools/train.py --data "$BIG" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" 2>&1 \
        | tee "$ART/$1-train.log" | grep -E "val   :|design|split"
    probe "$ART/$1.pjtw"
}
train_one A 1e-5
train_one B 1e-3

echo; echo "=== TRIANGLE vs handcrafted (depth 8) ==="
for tag in A B; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")"
done
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B

echo; echo "=== meilleur ($BEST) vs v15 — GATE MOVETIME (depth 9 + movetime 300) ==="
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null

echo; echo "=========================================================="
echo "        0161 RE-DISTILL sur 4.5M (v5+112) — VERDICT"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "  baselines (1.4M) : v4(32)=0.75  v5(40)=0.44  v5+ext=0.25"
echo "  → remonte = plus de data résorbe la sparsité → richesse débloquée."
echo "=========================================================="
