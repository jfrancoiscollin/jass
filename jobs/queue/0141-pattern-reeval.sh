#!/usr/bin/env bash
# id: 0141-pattern-reeval
# description: RÉÉVALUATION COMPLÈTE de l'approche pattern, autonome (ne
# dépend pas de 0140, mis en pause). On corrige les 3 confondants qui
# avaient « tué » le pattern et on le juge enfin proprement :
#   (a) labels : relabel PROPRE (fix ~18% captures forcées) — pas 0131 sale
#   (b) axe    : bench vs v15 en MOVETIME (sa vitesse ~100×), pas que depth
#   (c) search : SPSA-tune les constantes AVEC le pattern (pas réglées NNUE)
#
# Pipeline :
#   1. relabel master 1.5M Scan d10 PROPRE
#   2. handcrafted aligné (squelette résidu)
#   3. train pattern hybride (résidu = scan - hc)
#   4. bench vs handcrafted d6     (cf 0129=0.667, 0131=0.000)
#   5. bench vs v15 : depth 8 (vitesse invisible) + movetime 0.3s
#   6. SPSA-tune les constantes pour le pattern (depth 8)
#   7. re-bench : tuned-vs-default + pattern(tuné) vs v15 movetime
#
# expected_duration: ~1.5-2.5 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0141-pattern-reeval"
ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

SAMPLE=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/master-sample-1500K.jnnw
[ -f "$SAMPLE" ] || { echo "ABORT: master sample manquant"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "sample : $SAMPLE"; echo "v15 : $V15"

echo; echo "=== Phase 0 : deps ==="
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

# --- Scan (relabel a besoin de scan.ini + data/ dans le dossier) -----------
SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" || { echo "ABORT clone"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi

echo; echo "=== Phase 2 : relabel Scan d10 PROPRE (1.5M, $NCPU shards) ==="
TARGET_N=1500000; SHARD=$(( (TARGET_N + NCPU - 1) / NCPU )); FILES=(); pids=()
START_RL=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
    OUT_SH="$ART/shard-${sh}.jnnw"; FILES+=("$OUT_SH")
    ( python3 tools/relabel_with_scan.py --in "$SAMPLE" --out "$OUT_SH" \
        --scan "$SCAN_BIN" --depth 10 --start $(( sh*SHARD )) --max-records "$SHARD" \
        --timeout 60 --newgame-every 50 --progress-every 20000 \
        > "$ART/relabel-shard-${sh}.log" 2>&1 ) & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (shard $p rc!=0)"; done
echo "  relabel wall : $(( $(date +%s) - START_RL ))s"
CLEAN="$ART/master-clean-scan-d10.jnnw"
python3 - <<EOF
import struct
from pathlib import Path
shards=[$(printf '"%s",' "${FILES[@]}")]; total=0
with open("$CLEAN",'wb') as o:
    o.write(b"JNNW"); o.write(struct.pack("<I",0))
    for s in shards:
        r=Path(s).read_bytes(); n=struct.unpack_from('<I',r,4)[0]; o.write(r[8:8+n*38]); total+=n
    o.seek(4); o.write(struct.pack("<I",total))
print(f"merged {total} CLEAN records → $CLEAN")
EOF
SKIP=$(grep -hoE "skipped=[0-9]+" "$ART"/relabel-shard-*.log | awk -F= '{s+=$2} END{print s}')
echo "  positions exclues (Scan non-scorable) : ${SKIP:-?}"

echo; echo "=== Phase 3 : handcrafted aligné ==="
HC="$ART/master-clean-hc.jnnw"
./build-prod/jass --rewrite-scores-with-handcrafted "$CLEAN" "$HC" > "$ART/hc.log" 2>&1 || { echo "ABORT hc"; exit 4; }

echo; echo "=== Phase 4 : train pattern hybride sur labels PROPRES ==="
PAT="$ART/pattern_clean.pjtw"
python3 pattern_jass/tools/train.py --data "$CLEAN" --skeleton-data "$HC" \
    --out "$PAT" --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
    2>&1 | tee "$ART/pattern-train.log"
[ -f "$PAT" ] || { echo "ABORT train pattern"; exit 4; }

rate_pj () { grep -oE 'rate[^0-9]*[0-9.]+' "$1" | grep -oE '[0-9.]+$' | tail -1; }
rate_pv () { grep -oE 'PATTERN score rate vs NNUE: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

echo; echo "=== Phase 5 : bench pattern propre ==="
./build-prod/jass --benchmark-pattern-jass "$PAT" 6 3 2>&1 | tee "$ART/pat-vs-hc.log"
R_HC=$(rate_pj "$ART/pat-vs-hc.log")
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 8 5 1 0 "" 2>&1 | tee "$ART/pat-vs-v15-d8.log"
R_V15_D=$(rate_pv "$ART/pat-vs-v15-d8.log")
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 64 5 1 300 "" 2>&1 | tee "$ART/pat-vs-v15-mt.log"
R_V15_MT=$(rate_pv "$ART/pat-vs-v15-mt.log")

echo; echo "=== Phase 6 : SPSA-tune les constantes POUR le pattern (depth 8) ==="
BEST_JSON="$ART/spsa-best.json"
# 15 params (constantes + razoring/probcut/ext) → 60 iters pour converger.
# Le pattern décide LUI-MÊME si razoring/probcut/ext l'aident (pas le
# verdict NNUE de 0138).
python3 tools/spsa_tune.py --jass ./build-prod/jass --net "$PAT" \
    --iters 60 --pairs 4 --depth 8 --threads 1 --use-pvs 1 --out "$BEST_JSON" \
    2>&1 | tee "$ART/spsa.log"
BEST=$(python3 -c "import json;print(json.load(open('$BEST_JSON'))['spec'])" 2>/dev/null || echo "use_pvs=1")
echo "best spec : $BEST"

echo; echo "=== Phase 7 : re-bench avec constantes tunées ==="
./build-prod/jass --benchmark-search-params "$PAT" "$BEST" "use_pvs=1" 64 5 1 300 2>&1 | tee "$ART/tuned-vs-default-mt.log"
R_TD_MT=$(rate_sp "$ART/tuned-vs-default-mt.log")
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 64 5 1 300 "$BEST" 2>&1 | tee "$ART/pat-tuned-vs-v15-mt.log"
R_V15_MT_T=$(rate_pv "$ART/pat-tuned-vs-v15-mt.log")

echo; echo "=========================================================="
echo "        0141 RÉÉVALUATION PATTERN — VERDICT"
echo "=========================================================="
echo "  pattern propre : $PAT (exclus forcées : ${SKIP:-?})"
echo "  best spec : $BEST"
python3 - "${R_HC:-}" "${R_V15_D:-}" "${R_V15_MT:-}" "${R_TD_MT:-}" "${R_V15_MT_T:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
hc, v15d, v15mt, tdmt, v15mtt = sys.argv[1:6]
print(f"  (a) pattern vs handcrafted d6      : {hc or 'n/a':>6}   (0129=0.667, 0131=0.000)")
print(f"  (b) pattern vs v15  @ DEPTH 8      : {v15d or 'n/a':>6}  ELO {elo(v15d)}  (vitesse invisible)")
print(f"  (b) pattern vs v15  @ MOVETIME     : {v15mt or 'n/a':>6}  ELO {elo(v15mt)}  (vitesse compte)")
print(f"  (c) tuned vs default (mt)          : {tdmt or 'n/a':>6}  ELO {elo(tdmt)}")
print(f"  (c) pattern(TUNÉ) vs v15 @ MT      : {v15mtt or 'n/a':>6}  ELO {elo(v15mtt)}")
print()
def f(x):
    try: return float(x)
    except: return None
hcv=f(hc)
if hcv is not None:
    print("  (a) labels :", "0131 était plombé par les labels, pas l'archi" if hcv>=0.55 else "le pattern reste faible même avec labels propres")
d,mt=f(v15d),f(v15mt)
if d is not None and mt is not None:
    print(f"  (b) vitesse : vs v15 {d:.3f}→{mt:.3f} (depth→movetime), gain {mt-d:+.3f}")
    if mt < d - 0.03:
        print("      ⚠️  movetime < depth : la recherche profonde du pattern ne paie pas")
        print("         → watch-item time-mgmt haute profondeur (docs/archives/PATTERN_PROGRAM_NOTES.md §1)")
td=f(tdmt)
if td is not None:
    print("  (c) search :", "le pattern ÉTAIT bridé par une recherche réglée NNUE" if td>=0.53 else "le search n'était pas le facteur limitant")
mtt=f(v15mtt)
if mtt is not None:
    print(f"  → BILAN : pattern(propre+tuné) vs v15 à temps égal = {mtt:.3f}",
          "→ COMPÉTITIF, prioriser le pattern" if mtt>=0.50 else "→ encore derrière, mais sur quel facteur ?")
EOF
echo "=========================================================="
