#!/usr/bin/env bash
# id: 0141-pattern-search-tune
# description: Teste si le pattern est BRIDÉ par une recherche réglée pour
# le NNUE. Les constantes de pruning/réduction (RFP/NMP/singular/LMR/LMP/
# aspiration, en cp) ont été tunées pour la distribution de scores du NNUE.
# On les SPSA-tune AVEC le pattern comme éval, puis on valide :
#   1. tuned vs default (même pattern) → le search était-il mal réglé ?
#   2. pattern(tuned) vs v15 en movetime → compétitif une fois bien réglé ?
#
# Tuning à depth 8 (rapide/stable ; le pattern est ~100× plus rapide donc
# 2880 games passent vite). Validation à movetime (là où la vitesse paie).
# Caveat : des constantes tunées à depth 8 ne transfèrent pas parfaitement
# à la profondeur atteinte en movetime — 1er passage indicatif.
#
# expected_duration: ~1-2 h.
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0141-pattern-search-tune"
ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

# --- pattern : préférer le pattern PROPRE de 0140, sinon 0131 ---------------
PAT=/root/jass/jobs/results/0140-clean-distillation/artefacts.src/pattern_clean.pjtw
[ -f "$PAT" ] || PAT=/root/jass/jobs/results/0131-phase3-scan-bootstrap-full/artefacts.src/pattern_jass_v9_scan_full.pjtw
[ -f "$PAT" ] || PAT=$(find /root/jass/jobs/results -name '*.pjtw' 2>/dev/null | head -1)
[ -n "$PAT" ] && [ -f "$PAT" ] || { echo "ABORT: aucun pattern .pjtw trouvé"; exit 3; }
echo "pattern : $PAT"
V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 manquant"; exit 3; }
echo "v15     : $V15"

echo; echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy

BASE="use_pvs=1"   # défaut = PVS on + constantes NNUE-tunées

echo; echo "=== Phase 1 : SPSA-tune les constantes AVEC le pattern (depth 8) ==="
BEST_JSON="$ART/pattern-spsa-best.json"
python3 tools/spsa_tune.py --jass ./build-prod/jass --net "$PAT" \
    --iters 40 --pairs 4 --depth 8 --threads 1 --use-pvs 1 \
    --out "$BEST_JSON" 2>&1 | tee "$ART/spsa.log"
[ -f "$BEST_JSON" ] || { echo "ABORT: spsa"; exit 4; }
BEST=$(python3 -c "import json;print(json.load(open('$BEST_JSON'))['spec'])")
echo "best spec : $BEST"

rate_sp () { grep -oE 'A score rate: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }
rate_pv () { grep -oE 'PATTERN score rate vs NNUE: [0-9.]+' "$1" | grep -oE '[0-9.]+$' | head -1; }

echo; echo "=== Phase 2 : tuned vs default (MÊME pattern) — search mal réglé ? ==="
./build-prod/jass --benchmark-search-params "$PAT" "$BEST" "$BASE" 9 5 1 0 \
    2>&1 | tee "$ART/tuned-vs-default-d9.log"
R_TD_D=$(rate_sp "$ART/tuned-vs-default-d9.log")
./build-prod/jass --benchmark-search-params "$PAT" "$BEST" "$BASE" 64 5 1 300 \
    2>&1 | tee "$ART/tuned-vs-default-mt.log"
R_TD_MT=$(rate_sp "$ART/tuned-vs-default-mt.log")

echo; echo "=== Phase 3 : pattern vs v15 — default vs tuned, depth & movetime ==="
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 8 5 1 0 "" \
    2>&1 | tee "$ART/pat-vs-v15-d8-default.log"
R_PV_D_DEF=$(rate_pv "$ART/pat-vs-v15-d8-default.log")
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 64 5 1 300 "" \
    2>&1 | tee "$ART/pat-vs-v15-mt-default.log"
R_PV_MT_DEF=$(rate_pv "$ART/pat-vs-v15-mt-default.log")
./build-prod/jass --benchmark-pattern-vs-nnue "$PAT" "$V15" 64 5 1 300 "$BEST" \
    2>&1 | tee "$ART/pat-vs-v15-mt-tuned.log"
R_PV_MT_TUNED=$(rate_pv "$ART/pat-vs-v15-mt-tuned.log")

echo; echo "=========================================================="
echo "       0141 PATTERN SEARCH-TUNE — VERDICT"
echo "=========================================================="
echo "  pattern : $(basename "$PAT")"
echo "  best spec : $BEST"
python3 - "${R_TD_D:-}" "${R_TD_MT:-}" "${R_PV_D_DEF:-}" "${R_PV_MT_DEF:-}" "${R_PV_MT_TUNED:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
td_d, td_mt, pv_d_def, pv_mt_def, pv_mt_tuned = sys.argv[1:6]
print(f"  [1] tuned vs default pattern @ d9     : {td_d or 'n/a':>6}  ELO {elo(td_d)}")
print(f"  [1] tuned vs default pattern @ mt0.3s : {td_mt or 'n/a':>6}  ELO {elo(td_mt)}")
print(f"  [2] pattern vs v15  @ d8  (default)   : {pv_d_def or 'n/a':>6}  ELO {elo(pv_d_def)}")
print(f"  [2] pattern vs v15  @ mt  (default)   : {pv_mt_def or 'n/a':>6}  ELO {elo(pv_mt_def)}")
print(f"  [2] pattern vs v15  @ mt  (TUNED)     : {pv_mt_tuned or 'n/a':>6}  ELO {elo(pv_mt_tuned)}")
print()
def f(x):
    try: return float(x)
    except: return None
td=f(td_mt)
if td is not None:
    if td >= 0.53:
        print("  → [1] OUI : le pattern était bridé par une recherche réglée NNUE.")
        print("        Tuner les constantes pour le pattern le renforce.")
    else:
        print("  → [1] le search n'était pas le facteur limitant majeur du pattern.")
d_def,m_def,m_tun=f(pv_d_def),f(pv_mt_def),f(pv_mt_tuned)
if m_def is not None and d_def is not None:
    print(f"  → [2] vitesse : pattern vs v15 passe de {d_def:.3f} (depth) à {m_def:.3f} (movetime)")
if m_tun is not None and m_def is not None:
    print(f"        + tuning : {m_def:.3f} → {m_tun:.3f} en movetime")
    if m_tun >= 0.50:
        print("        → pattern(tuné) >= v15 à TEMPS ÉGAL : path pattern à prioriser.")
EOF
echo "=========================================================="
