#!/usr/bin/env bash
# id: 0140-clean-distillation
# description: Re-distillation PROPRE après fix du relabel (~18% des labels
# 'Scan d10' étaient en fait les labels originaux — positions à capture
# forcée que l'ancien parser jetait). On relabel le sample master avec le
# relabel corrigé (scores Scan 100% réels, positions non-scorables
# exclues), puis on entraîne ET benche les DEUX cibles sur ces mêmes
# labels propres :
#   - NNUE 128-64 (archi v15)  → bench vs v15 (in-process) + vs Scan d10
#   - Pattern hybride (résidu)  → bench vs handcrafted (cf 0129=0.667, 0131=0.000)
#
# Question : nos distillations précédentes étaient-elles plombées par les
# 18% de faux labels ? Si le NNUE propre bat v15 et/ou le pattern propre
# remonte vs 0131, OUI — il faut re-distiller proprement partout.
#
# expected_duration: ~1.5-2.5 h (relabel 1.5M sharded ~20min + 2 trainings
# + benches).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0140-clean-distillation"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

# --- inputs ----------------------------------------------------------------
SAMPLE=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/master-sample-1500K.jnnw
[ -f "$SAMPLE" ] || { echo "ABORT: master sample 0131 manquant"; exit 3; }
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "sample : $SAMPLE"
echo "v15    : $V15"

echo; echo "=== Phase 0 : deps (numpy/torch/scipy) ==="
python3 -c "import numpy, torch, scipy" 2>/dev/null || {
    PIP=/root/jass/.pip-scratch; mkdir -p "$PIP"
    for a in 1 2 3; do TMPDIR="$PIP" pip3 install --break-system-packages --no-cache-dir --quiet numpy torch scipy && break; sleep 5; done
    rm -rf "$PIP"; }

echo; echo "=== Phase 1 : build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

# --- Scan install (relabel a besoin de scan.ini + data/ dans le dossier) ----
SCAN_DIR=/root/jass-scan
SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
    SRC=/root/jass-scan-src
    [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" \
        || { echo "ABORT: clone scan"; exit 4; }
    mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
    cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true
    cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
echo "scan : $SCAN_BIN"

# --- Phase 2 : relabel PROPRE (relabel corrigé, drop-skipped par défaut) ----
echo; echo "=== Phase 2 : relabel Scan d10 PROPRE (1.5M, $NCPU shards) ==="
TARGET_N=1500000
SHARD_SIZE=$(( (TARGET_N + NCPU - 1) / NCPU ))
SHARD_FILES=()
pids=()
START_RL=$(date +%s)
for sh in $(seq 0 $((NCPU-1))); do
    START=$(( sh * SHARD_SIZE ))
    OUT_SH="$ART/shard-${sh}.jnnw"; SHARD_FILES+=("$OUT_SH")
    ( python3 tools/relabel_with_scan.py --in "$SAMPLE" --out "$OUT_SH" \
        --scan "$SCAN_BIN" --depth 10 --start "$START" --max-records "$SHARD_SIZE" \
        --timeout 60 --newgame-every 50 --progress-every 20000 \
        > "$ART/relabel-shard-${sh}.log" 2>&1 ) &
    pids+=($!)
done
for p in "${pids[@]}"; do wait "$p" || echo "  (shard pid $p rc!=0)"; done
echo "  relabel wall : $(( $(date +%s) - START_RL ))s"

CLEAN="$ART/master-clean-scan-d10.jnnw"
python3 - <<EOF
import struct
from pathlib import Path
shards = [$(printf '"%s",' "${SHARD_FILES[@]}")]
total = 0
with open("$CLEAN", 'wb') as out:
    out.write(b"JNNW"); out.write(struct.pack("<I", 0))
    for sh in shards:
        raw = Path(sh).read_bytes()
        n = struct.unpack_from('<I', raw, 4)[0]
        out.write(raw[8:8 + n*38]); total += n
    out.seek(4); out.write(struct.pack("<I", total))
print(f"merged {total} CLEAN scan-labelled records → $CLEAN")
EOF
# taux de skip agrégé (combien de positions Scan-non-scorables exclues)
SKIP=$(grep -hoE "skipped=[0-9]+" "$ART"/relabel-shard-*.log | awk -F= '{s+=$2} END{print s}')
echo "  positions exclues (Scan non-scorable, forcées) : ${SKIP:-?}"

# --- Phase 3 : skeleton handcrafted ALIGNÉ sur les positions propres -------
echo; echo "=== Phase 3 : handcrafted aligné (pour le résidu pattern) ==="
HC="$ART/master-clean-handcrafted.jnnw"
./build-prod/jass --rewrite-scores-with-handcrafted "$CLEAN" "$HC" > "$ART/hc.log" 2>&1 \
    || { echo "ABORT: hc rewrite"; tail "$ART/hc.log"; exit 4; }

# =====================  BRANCHE NNUE  =======================================
echo; echo "=== Phase 4 : NNUE 128-64 sur labels PROPRES ==="
NN_DIR="$ART/nnue"; mkdir -p "$NN_DIR"
python3 tools/train_v3.py --data "$CLEAN" --archs 128-64 --encoding halfmen \
    --epochs 30 --batch 512 --wdl-scale 400 --bce-scale 50000 \
    --out-dir "$NN_DIR" 2>&1 | tee "$NN_DIR/train.log"
CLEAN_BIN="$NN_DIR/nnue-128-64.bin"; CLEAN_Q="$NN_DIR/nnue-128-64-q.bin"
python3 tools/quantize_mlp.py --in "$CLEAN_BIN" --data "$CLEAN" --out "$CLEAN_Q" \
    2>&1 | tee "$NN_DIR/quantize.log"

echo "--- bench NNUE-propre vs v15 (in-process, d10) ---"
./build-prod/jass --benchmark-nnue-vs-nnue "$CLEAN_Q" "$V15" 10 3 1 0 \
    2>&1 | tee "$ART/bench-nnue-vs-v15.log"
RATE_NN_V15=$(grep -oE 'A score rate: [0-9.]+' "$ART/bench-nnue-vs-v15.log" | grep -oE '[0-9.]+$' | head -1)

echo "--- bench NNUE-propre vs Scan d10 (bridge CORRIGÉ) ---"
SCAN_CAL=/root/jass/.scan
[ -x "$SCAN_CAL/scan_linux" ] || { rm -rf "$SCAN_CAL"; git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_CAL" 2>/dev/null; chmod +x "$SCAN_CAL/scan_linux"; }
python3 tools/calibrate_vs_scan.py --jass /root/jass/build-prod/jass \
    --scan "$SCAN_CAL/scan_linux" --nnue "$CLEAN_Q" --depth 10 --pairs 3 \
    2>&1 | tee "$ART/bench-nnue-vs-scan-d10.log"
RATE_NN_SCAN=$(grep -oE 'score rate[^0-9]*[0-9.]+' "$ART/bench-nnue-vs-scan-d10.log" | grep -oE '[0-9.]+$' | head -1)
ILL_NN=$(grep -cE 'illegal move' "$ART/bench-nnue-vs-scan-d10.log" 2>/dev/null || echo 0)

# =====================  BRANCHE PATTERN  ====================================
echo; echo "=== Phase 5 : pattern hybride sur labels PROPRES (résidu = scan - hc) ==="
PAT="$ART/pattern_clean.pjtw"
python3 pattern_jass/tools/train.py --data "$CLEAN" --skeleton-data "$HC" \
    --out "$PAT" --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000 \
    2>&1 | tee "$ART/pattern-train.log"

echo "--- bench pattern-propre vs handcrafted (d6, cf 0129=0.667 / 0131=0.000) ---"
./build-prod/jass --benchmark-pattern-jass "$PAT" 6 3 \
    2>&1 | tee "$ART/bench-pattern-vs-hc.log"
RATE_PAT_HC=$(grep -oE 'rate[^0-9]*[0-9.]+' "$ART/bench-pattern-vs-hc.log" | grep -oE '[0-9.]+$' | tail -1)

# =====================  VERDICT  ===========================================
echo; echo "=========================================================="
echo "        0140 DISTILLATION PROPRE — VERDICT"
echo "=========================================================="
echo "  labels propres : $CLEAN (exclus forcées : ${SKIP:-?})"
echo "  illegal bench NNUE-vs-Scan (doit être 0, bridge corrigé) : $ILL_NN"
python3 - "${RATE_NN_V15:-}" "${RATE_NN_SCAN:-}" "${RATE_PAT_HC:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
nn_v15, nn_scan, pat_hc = sys.argv[1:4]
print(f"  NNUE-propre vs v15      : rate {nn_v15 or 'n/a':>6}  ELO {elo(nn_v15)}")
print(f"  NNUE-propre vs Scan d10 : rate {nn_scan or 'n/a':>6}  ELO {elo(nn_scan)}")
print(f"  pattern-propre vs handcr: rate {pat_hc or 'n/a':>6}  (0129=0.667, 0131=0.000)")
print()
print("  Lecture :")
print("   - NNUE vs v15 > 0.55  → les 18% de faux labels plombaient v15 → re-distiller partout")
print("   - NNUE vs Scan d10     → 1re mesure éval-vs-Scan à prof. égale sur labels PROPRES")
print("   - pattern vs hc remonte vers ~0.667 → 0131 était plombé par les labels, pas l'archi")
EOF
echo "=========================================================="
