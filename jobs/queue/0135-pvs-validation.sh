#!/usr/bin/env bash
# id: 0135-pvs-validation
# description: Phase 1 (search) — valide PVS (Principal Variation Search)
# sur le réseau v15, en A/B un seul process (--benchmark-search-params).
#   - à profondeur fixe : PVS doit être ~neutre (sanity, pas de régression)
#   - à temps fixe (mt) : PVS cherche plus profond pour le même budget →
#     c'est LÀ que le gain ELO apparaît. C'est le test qui compte.
# Gate : si rate(use_pvs=1 vs 0) à mt >= 0.53 → on bascule use_pvs par
# défaut à 1 (commit suivant). Sinon → on garde PVS off et on investigue.
#
# expected_duration: ~1-2 h (2 matches ; le match mt domine).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0135-pvs-validation"
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

echo
echo "=== A. profondeur fixe d9, 90 games (sanity ~neutre) ==="
./build-prod/jass --benchmark-search-params "$V15" "use_pvs=1" "use_pvs=0" 9 5 1 0 \
    2>&1 | tee "$ART/A-depth9.log"
RATE_D=$(grep -oE 'A score rate: [0-9.]+' "$ART/A-depth9.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=== B. temps fixe 0.3s/coup, 90 games (LE test) ==="
./build-prod/jass --benchmark-search-params "$V15" "use_pvs=1" "use_pvs=0" 64 5 1 300 \
    2>&1 | tee "$ART/B-movetime300.log"
RATE_T=$(grep -oE 'A score rate: [0-9.]+' "$ART/B-movetime300.log" | grep -oE '[0-9.]+$' | head -1)

echo
echo "=========================================================="
echo "        0135 PVS VALIDATION — VERDICT"
echo "=========================================================="
python3 - "${RATE_D:-}" "${RATE_T:-}" <<'EOF'
import sys, math
def elo(r):
    try: r=float(r)
    except: return "n/a"
    if r<=0: return "-inf"
    if r>=1: return "+inf"
    return f"{-400*math.log10(1/r-1):+.0f}"
d,t=sys.argv[1],sys.argv[2]
print(f"  profondeur fixe d9 : rate {d or 'n/a'}  ELO {elo(d)}  (attendu ~0.50)")
print(f"  temps fixe 0.3s    : rate {t or 'n/a'}  ELO {elo(t)}  (LE test)")
print()
try: tt=float(t)
except: tt=None
if tt is None:
    print("  → pas de rate mt parsé, voir B-movetime300.log")
elif tt >= 0.53:
    print("  → PVS PASS — basculer use_pvs=1 par défaut (commit suivant).")
else:
    print("  → PVS neutre/négatif à temps fixe. Garder off, investiguer "
          "(interaction TT/bounds, ordre des re-searches).")
EOF
echo "=========================================================="
