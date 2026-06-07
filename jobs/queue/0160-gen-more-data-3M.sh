#!/usr/bin/env bash
# id: 0160-gen-more-data-3M
# description: AXE QUALITÉ support — PLUS DE DONNÉES. 0159/0155 ont montré que la
# géométrie 40-patterns sur-sparsifie le 1.4M (val s'améliore mais le jeu
# régresse 0.75→0.44→0.25). Décision : +3M positions self-play, relabelisées
# Scan-d10, mergées avec le 1.4M existant → ~4.5M, pour casser la sparsité.
#
# Pipeline :
#   1. gen self-play (handcrafted, ouvertures randomisées, SHARDÉ via seed) → 3M
#   2. convert JNNT(37o)→JNNW(38o, +byte wdl=0)
#   3. relabel Scan-d10 (binaire Scan GPL3, HUB v2, sharded)
#   4. merge avec master-clean-scan-d10 (1.4M) → master-clean-scan-d10-4p5M.jnnw
#
# expected_duration: ~1.5-3 h (relabel Scan-d10 de 3M = le gros).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0160-gen-more-data-3M"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

EXIST=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$EXIST" ] || { echo "ABORT: dataset 1.4M existant manquant"; exit 3; }
echo "existant (1.4M) : $EXIST"

echo; echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy

# --- Scan binaire (relabel) : scan.ini + data/ requis dans le dossier --------
SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" || { echo "ABORT clone"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: scan binaire indisponible"; exit 4; }

TOTAL=3000000; PER=$(( (TOTAL + NCPU - 1) / NCPU ))
echo; echo "=== 1) gen self-play $TOTAL positions ($NCPU shards × $PER) ==="
pids=(); shards=()
for sh in $(seq 0 $((NCPU-1))); do
    out="$ART/gen-${sh}.jnnt"; shards+=("$out")
    ./build-prod/jass --gen-data "$PER" "$out" "$(( 1000 + sh ))" > "$ART/gen-${sh}.log" 2>&1 & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (gen shard $p rc!=0)"; done

echo; echo "=== 2) convert JNNT(37o)→JNNW(38o) + merge shards ==="
RAW="$ART/selfplay-3M.jnnw"
python3 - "$RAW" "${shards[@]}" <<'PYEOF'
import struct, sys
from pathlib import Path
out=sys.argv[1]; shards=sys.argv[2:]; total=0
with open(out,'wb') as o:
    o.write(b'JNNW'); o.write(struct.pack('<I',0))
    for s in shards:
        r=Path(s).read_bytes()
        assert r[:4]==b'JNNT', f'{s}: bad magic'
        n=struct.unpack_from('<I',r,4)[0]; off=8
        for i in range(n):
            rec=r[off:off+37]; off+=37          # 32 bbs + 1 stm + 4 score
            o.write(rec); o.write(b'\x00')        # append wdl=0 → 38o JNNW
        total+=n
        Path(s).unlink(missing_ok=True)
    o.seek(4); o.write(struct.pack('<I',total))
print(f'merged+converted {total} self-play records → {out}')
PYEOF
rm -f "$ART"/gen-*.log

echo; echo "=== 3) relabel Scan-d10 (sharded) ==="
N=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$RAW','rb').read(8),4)[0])")
SHARD=$(( (N + NCPU - 1) / NCPU )); pids=(); rshards=()
START_RL=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
    o="$ART/relab-${sh}.jnnw"; rshards+=("$o")
    ( python3 tools/relabel_with_scan.py --in "$RAW" --out "$o" \
        --scan "$SCAN_BIN" --depth 10 --start $(( sh*SHARD )) --max-records "$SHARD" \
        > "$ART/relab-${sh}.log" 2>&1 ) & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (relabel shard $p rc!=0)"; done
echo "  relabel wall : $(( $(date +%s) - START_RL ))s"
SKIP=$(grep -hoE "skipped=[0-9]+" "$ART"/relab-*.log 2>/dev/null | awk -F= '{s+=$2} END{print s+0}')
echo "  skipped (Scan KO) : ${SKIP:-0}"

echo; echo "=== 4) merge relabel-shards + le 1.4M existant → ~4.5M ==="
BIG="$ART/master-clean-scan-d10-4p5M.jnnw"
python3 - "$BIG" "$EXIST" "${rshards[@]}" <<'PYEOF'
import struct, sys
from pathlib import Path
out=sys.argv[1]; ins=sys.argv[2:]; total=0; REC=38
with open(out,'wb') as o:
    o.write(b'JNNW'); o.write(struct.pack('<I',0))
    for s in ins:
        r=Path(s).read_bytes()
        assert r[:4]==b'JNNW', f'{s}: bad magic'
        n=struct.unpack_from('<I',r,4)[0]
        o.write(r[8:8+n*REC]); total+=n
    o.seek(4); o.write(struct.pack('<I',total))
print(f'merged {total} records → {out}')
PYEOF
rm -f "$ART"/relab-*.jnnw "$RAW"
NB=$(python3 -c "import struct;print(struct.unpack_from('<I',open('$BIG','rb').read(8),4)[0])")

echo; echo "=========================================================="
echo "        0160 PLUS DE DONNÉES — RÉSULTAT"
echo "  dataset final : $BIG"
echo "  records : $NB  (existant 1.4M + ~3M self-play relabelisés Scan-d10)"
echo "  → re-distiller v5 (40 patterns) dessus (0161) : la sparsité se résorbe ?"
echo "=========================================================="
