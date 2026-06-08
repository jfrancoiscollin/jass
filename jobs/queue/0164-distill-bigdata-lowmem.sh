#!/usr/bin/env bash
# id: 0164-distill-bigdata-lowmem
# description: Test BONNE DATA, version basse-mémoire. 0162 a produit le master
# COMPLET relabelisé Scan-d10 (4.70M, vraie data) mais son fit a fait OOM :
# l'optim L-BFGS-B à 42.5M dims (v5 40 patterns) prend ~8GB rien que pour son
# historique (maxcor=10) + la design matrix → OOM. train.py corrigé : float32
# (design + extras) + maxcor=5 → ~½ mémoire. On re-distille v5 sur le master-
# full (4.70M) avec la version basse-mémoire. (Les 2M v15-depth20 de 0106 ont
# été purgés du runner → on s'en passe ; 4.70M master = déjà 3× le 1.4M.)
#
# Baselines : v4(32,1.4M)=0.75 ; v5(40,1.4M)=0.44 ; v5+ext-cheap-4M=0.11.
# Lecture : > 0.44 (et idéalement > 0.75) = la vraie data débloque la richesse.
#
# expected_duration: ~2-4 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0164-distill-bigdata-lowmem"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU  RAM: $(free -g 2>/dev/null | awk '/Mem/{print $2"G"}') ==="

BIG=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$BIG" ] || { echo "ABORT: master-full (0162) absent — purgé ?"; exit 3; }
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$BIG','rb').read(8),4)[0])")
[ "$NB" -ge 3000000 ] || { echo "ABORT: dataset trop petit ($NB)"; exit 3; }
echo "master-full : $BIG ($NB records)"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# Réutilise le dump features de 0162 (112 col) s'il persiste, sinon re-dump.
FEAT=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/full112.feat
if [ ! -f "$FEAT" ]; then FEAT="$ART/full112.feat"; ./build-prod/jass --dump-eval-features "$BIG" "$FEAT" 2>&1 | tail -1; fi
echo "feat: $FEAT"

anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
train_one () {
    echo; echo "=== TRAIN $1 (v5+112 sur $NB, low-mem maxcor=5 float32, l2=$2) ==="
    python3 pattern_jass/tools/train.py --data "$BIG" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" 2>&1 \
        | tee "$ART/$1-train.log" | grep -E "val   :|design|split" | sed 's/^/    /'
}
train_one A 1e-5
train_one B 1e-3
for tag in A B; do
    [ -f "$ART/$tag.pjtw" ] || { echo "  $tag : pas de modèle (échec/OOM train)"; continue; }
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")"
done
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B
if [ -f "$ART/$BEST.pjtw" ]; then
  ./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
  ./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null
fi

echo; echo "=========================================================="
echo "        0164 BONNE DATA 4.70M (v5, low-mem) — VERDICT"
echo "  records : $NB"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "  baselines : v4(32,1.4M)=0.75  v5(40,1.4M)=0.44  cheap-4M=0.11"
echo "  → > 0.44 = la vraie data aide ; > 0.75 = elle débloque la richesse."
echo "=========================================================="
