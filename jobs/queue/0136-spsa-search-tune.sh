#!/usr/bin/env bash
# id: 0136-spsa-search-tune
# description: Phase 1 (search) — premier passage SPSA sur les constantes
# de recherche (RFP/NMP/singular/LMR/LMP/aspiration), réseau v15, PVS
# tenu à 1. Puis VALIDATION du meilleur spec vs le défaut sur un match
# frais plus large. Ship le spec uniquement si rate >= 0.53.
#
# Note : le tuning à temps fixe (movetime) est le plus pertinent une fois
# PVS validé (0135). On tune ici à profondeur fixe d8 (rapide, stable)
# puis on valide À LA FOIS en depth ET en movetime.
#
# expected_duration: ~3-6 h (40 iters × 72 games + validation). Ajuster
# --iters/--pairs pour le budget.
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0136-spsa-search-tune"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"   # /tmp runner trop petit pour l'assembleur

V15=$(ls -t /root/jass/jobs/results/0090-small-arch-sweep-movetime/artefacts.src/arch-128-64/nnue-*-q.bin 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -n "$V15" ] && [ -f "$V15" ] || { echo "ABORT: v15 weights manquants"; exit 3; }
echo "v15 : $V15"

echo "=== build prod ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || {
    echo "BUILD FAIL"; tail -30 "$ART/build.log"; exit 5; }

BEST_JSON="$ART/spsa-best.json"
echo
echo "=== SPSA tuning (40 iters, 72 games/iter, d8, PVS on) ==="
python3 tools/spsa_tune.py \
    --jass ./build-prod/jass --net "$V15" \
    --iters 40 --pairs 4 --depth 8 --threads 1 --use-pvs 1 \
    --out "$BEST_JSON" 2>&1 | tee "$ART/spsa.log"
[ -f "$BEST_JSON" ] || { echo "ABORT: spsa n'a pas produit de best"; exit 4; }
BEST_SPEC=$(python3 -c "import json;print(json.load(open('$BEST_JSON'))['spec'])")
echo "best spec : $BEST_SPEC"

# Baseline = défauts + PVS on (on isole le gain du tuning, pas de PVS).
BASE_SPEC="use_pvs=1"

echo
echo "=== Validation A : best vs baseline, depth 9, 162 games ==="
./build-prod/jass --benchmark-search-params "$V15" "$BEST_SPEC" "$BASE_SPEC" 9 9 1 0 \
    2>&1 | tee "$ART/validate-depth9.log"
RATE_VD=$(grep -oE 'A score rate: [0-9.]+' "$ART/validate-depth9.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=== Validation B : best vs baseline, movetime 0.3s, 162 games ==="
./build-prod/jass --benchmark-search-params "$V15" "$BEST_SPEC" "$BASE_SPEC" 64 9 1 300 \
    2>&1 | tee "$ART/validate-movetime300.log"
RATE_VT=$(grep -oE 'A score rate: [0-9.]+' "$ART/validate-movetime300.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=========================================================="
echo "        0136 SPSA SEARCH-TUNE — VERDICT"
echo "=========================================================="
echo "  best spec : $BEST_SPEC"
python3 - "${RATE_VD:-}" "${RATE_VT:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
d,t=sys.argv[1],sys.argv[2]
print(f"  best vs default  depth9 : rate {d or 'n/a'}  ELO {elo(d)}")
print(f"  best vs default  mt0.3s : rate {t or 'n/a'}  ELO {elo(t)}")
print()
def f(x):
    try: return float(x)
    except: return None
best = max([v for v in (f(d),f(t)) if v is not None], default=None)
if best is None:
    print("  → pas de rate parsé.")
elif best >= 0.53:
    print("  → SPSA PASS — committer ces constantes comme nouveaux défauts "
          "dans src/search_params.hpp.")
else:
    print("  → gain SPSA non significatif. Relancer avec plus d'iters/games "
          "ou tuner directement à movetime.")
EOF
echo "=========================================================="
