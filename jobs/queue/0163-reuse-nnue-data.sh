#!/usr/bin/env bash
# id: 0163-reuse-nnue-data
# description: BONNE DATA (suite) — réutilise la data NNUE déjà générée. 0106 a
# produit 2M positions en self-play du NNUE v15 À DEPTH 20 (joueur fort +
# recherche profonde = bonne data, ≠ handcrafted-d4 de 0161). On la relabel
# Scan-d10 et on la merge avec le master-FULL (de 0162) → la plus grosse +
# diverse bonne data, puis on distille v5.
#
# Lecture : si > 0162 (master seul) et surtout > v4(0.75) → la VRAIE data
# (forte + volumineuse) débloque la richesse. C'est le test décisif de
# l'hypothèse data.
#
# expected_duration: ~2.5-4 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0163-reuse-nnue-data"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

NNUE_DATA=/root/jass/jobs/results/0106-gen-data-depth20-2M/artefacts.src/gen-2M-depth20.bin
[ -f "$NNUE_DATA" ] || { echo "ABORT: data NNUE 0106 (2M depth20) manquante"; exit 3; }
MASTER_FULL=/root/jass/jobs/results/0162-good-data-full-master/artefacts.src/master-full-scan-d10.jnnw
[ -f "$MASTER_FULL" ] || { echo "ABORT: master-full (0162) manquant — 0162 a-t-il réussi ?"; exit 3; }
ND=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$NNUE_DATA','rb').read(8),4)[0])")
MF=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$MASTER_FULL','rb').read(8),4)[0])")
echo "data NNUE (v15 depth20) : $ND records"; echo "master-full Scan-d10 : $MF records"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" || { echo "ABORT clone"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan indisponible"; exit 4; }

echo; echo "=== relabel la data NNUE (2M) en Scan-d10 (sharded) ==="
SHARD=$(( (ND + NCPU - 1) / NCPU )); pids=(); rshards=(); START_RL=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
    o="$ART/relab-${sh}.jnnw"; rshards+=("$o")
    ( python3 tools/relabel_with_scan.py --in "$NNUE_DATA" --out "$o" \
        --scan "$SCAN_BIN" --depth 10 --start $(( sh*SHARD )) --max-records "$SHARD" \
        > "$ART/relab-${sh}.log" 2>&1 ) & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (relabel shard $p rc!=0)"; done
echo "  relabel wall : $(( $(date +%s) - START_RL ))s"

echo; echo "=== merge : master-full + NNUE-2M-relabelisé → big-good ==="
BIG="$ART/big-good-scan-d10.jnnw"
python3 - "$BIG" "$MASTER_FULL" "${rshards[@]}" <<'PYEOF'
import struct, sys
from pathlib import Path
out=sys.argv[1]; ins=sys.argv[2:]; total=0; REC=38
with open(out,'wb') as o:
    o.write(b'JNNW'); o.write(struct.pack('<I',0))
    for s in ins:
        r=Path(s).read_bytes(); assert r[:4]==b'JNNW'; n=struct.unpack_from('<I',r,4)[0]
        o.write(r[8:8+n*REC]); total+=n
        if 'relab-' in s: Path(s).unlink(missing_ok=True)
    o.seek(4); o.write(struct.pack('<I',total))
print(f'big-good : {total} records → {out}')
PYEOF
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$BIG','rb').read(8),4)[0])")
echo "  big-good : $NB records (master-full + 2M v15-depth20)"

echo; echo "=== dump features (112) + distillation v5 ==="
FEAT="$ART/big112.feat"; ./build-prod/jass --dump-eval-features "$BIG" "$FEAT" 2>&1 | tail -1
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
train_one () {
    echo; echo "=== TRAIN $1 (v5+112 sur big-good, l2=$2) ==="
    python3 pattern_jass/tools/train.py --data "$BIG" --scan-eval --eval-features-file "$FEAT" \
        --target score --score-clip 5000 --l2 "$2" --max-iter 200 --scale 1000 \
        --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/$1.pjtw" 2>&1 \
        | tee "$ART/$1-train.log" | grep -E "val   :|split"
}
train_one A 1e-5
train_one B 1e-3
for tag in A B; do
    ./build-prod/jass --benchmark-scan-eval "$ART/$tag.pjtw" hc 8 3 1 0 "" 64 2>&1 | tee "$ART/$tag-vs-hc.log" >/dev/null
    echo "  $tag vs hc = $(anyrate "$ART/$tag-vs-hc.log")"
done
BEST=A; RA=$(anyrate "$ART/A-vs-hc.log"); RB=$(anyrate "$ART/B-vs-hc.log")
python3 -c "import sys;a=float('${RA:-0}' or 0);b=float('${RB:-0}' or 0);sys.exit(0 if a>=b else 1)" && BEST=A || BEST=B
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 9  3 1 0   "" 64 2>&1 | tee "$ART/$BEST-vs-v15-d9.log" >/dev/null
./build-prod/jass --benchmark-scan-eval "$ART/$BEST.pjtw" "$V15" 64 3 1 300 "" 64 2>&1 | tee "$ART/$BEST-vs-v15-mt.log" >/dev/null

echo; echo "=========================================================="
echo "        0163 BONNE DATA (master + v15-depth20) — VERDICT"
echo "  big-good : $NB records"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "  baselines : v4(32,1.5M)=0.75  v5(40,1.5M)=0.44  v5+ext-cheap-4M=0.11"
echo "  → > 0.75 = la VRAIE data forte débloque enfin la richesse."
echo "=========================================================="
