#!/usr/bin/env bash
# id: 0162-good-data-full-master
# description: BONNE DATA. 0161 a montré que le self-play handcrafted-d4 est de
# la MAUVAISE data (étroite, basse qualité → jeu effondré 0.25→0.11). Retour à
# la source PROUVÉE : jeux de maîtres. 0131 n'avait pris qu'un sous-échantillon
# 1.5M du pool master-1600 COMPLET — on relabel le pool ENTIER en Scan-d10 (plus
# de VRAIE data) et on distille v5 (40 pat + 112 extras) dessus.
#
# Lecture : si v5 sur master-FULL > v5 sur 1.5M (0.44) voire > v4 (0.75) → la
# bonne data débloque la richesse. Si pool ≈ 1.5M (pas de surplus) → on saura
# qu'il faut fetch plus / self-play FORT.
# Baselines : v4(32,1.5M)=0.75 ; v5(40,1.5M)=0.44 ; v5+ext(40,112,1.5M)=0.25.
#
# expected_duration: ~2-4 h (relabel Scan-d10 du pool + fit).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0162-good-data-full-master"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

MASTER=/root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw
[ -f "$MASTER" ] || { echo "ABORT: pool master-1600 manquant"; exit 3; }
NM=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$MASTER','rb').read(8),4)[0])")
echo "pool master-1600 COMPLET : $MASTER  ($NM records ; le sous-échantillon était 1.5M)"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }

echo; echo "=== build prod + tests ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
./build-prod/jass_tests > "$ART/tests.log" 2>&1 && echo "TESTS PASS" || { echo TESTS FAIL; tail -20 "$ART/tests.log"; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- Scan binaire ------------------------------------------------------------
SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" || { echo "ABORT clone"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan indisponible"; exit 4; }

echo; echo "=== relabel master-1600 COMPLET en Scan-d10 (sharded) ==="
SHARD=$(( (NM + NCPU - 1) / NCPU )); pids=(); rshards=(); START_RL=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
    o="$ART/relab-${sh}.jnnw"; rshards+=("$o")
    ( python3 tools/relabel_with_scan.py --in "$MASTER" --out "$o" \
        --scan "$SCAN_BIN" --depth 10 --start $(( sh*SHARD )) --max-records "$SHARD" \
        > "$ART/relab-${sh}.log" 2>&1 ) & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (relabel shard $p rc!=0)"; done
echo "  relabel wall : $(( $(date +%s) - START_RL ))s"

CLEAN="$ART/master-full-scan-d10.jnnw"
python3 - "$CLEAN" "${rshards[@]}" <<'PYEOF'
import struct, sys
from pathlib import Path
out=sys.argv[1]; ins=sys.argv[2:]; total=0; REC=38
with open(out,'wb') as o:
    o.write(b'JNNW'); o.write(struct.pack('<I',0))
    for s in ins:
        r=Path(s).read_bytes(); assert r[:4]==b'JNNW'; n=struct.unpack_from('<I',r,4)[0]
        o.write(r[8:8+n*REC]); total+=n
        Path(s).unlink(missing_ok=True)
    o.seek(4); o.write(struct.pack('<I',total))
print(f'master-full Scan-d10 : {total} records → {out}')
PYEOF
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$CLEAN','rb').read(8),4)[0])")
echo "  dataset bonne-data : $NB records (vs 1.5M sous-échantillon)"

echo; echo "=== dump-eval-features (112) + distillation v5 ==="
FEAT="$ART/full112.feat"; ./build-prod/jass --dump-eval-features "$CLEAN" "$FEAT" 2>&1 | tail -1
anyrate () { grep -oE 'score rate[^0-9]*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+$' | head -1; }
train_one () {
    echo; echo "=== TRAIN $1 (v5+112 sur master-FULL, l2=$2) ==="
    python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$FEAT" \
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
echo "        0162 BONNE DATA (master-FULL Scan-d10) — VERDICT"
echo "  pool : $NB records (master-1600 complet)"
echo "  A vs hc=${RA:-?}  B vs hc=${RB:-?}"
echo "  $BEST vs v15 : d9=$(anyrate "$ART/$BEST-vs-v15-d9.log")  mt=$(anyrate "$ART/$BEST-vs-v15-mt.log")"
echo "  baselines(1.5M) : v4=0.75  v5=0.44  v5+ext=0.25 ; v5+ext sur 4.1M(cheap)=0.11"
echo "  → > 0.44 = vraie data débloque la richesse ; ≈ → pool master épuisé."
echo "=========================================================="
