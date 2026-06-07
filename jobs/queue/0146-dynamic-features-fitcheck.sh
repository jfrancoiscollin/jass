#!/usr/bin/env bash
# id: 0146-dynamic-features-fitcheck
# description: PRÉ-CHECK final "pattern plus riche" — le résidu Scan−handcrafted
# est-il STATIQUE-ajoutable (kings/balance) ou DYNAMIQUE (mobilité/tactique,
# uncapturable par un pattern statique) ? On dumpe les features mobilité +
# balance via le moteur (movegen exact) et on regarde si le val_mse chute.
#   men-only → men+mobilité/balance → men+tout(king+mob/bal)
# Si même tout ça ne fait quasi rien → le résidu est de la tactique profonde
# → aucun pattern statique ne gagnera → repivot NNUE assumé.
# Cheap, sans parties.
# expected_duration: ~20-40 min (dump + 3 fits).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0146-dynamic-features-fitcheck"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname) ==="
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
HC=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-hc.jnnw
[ -f "$CLEAN" ] && [ -f "$HC" ] || { echo "ABORT: labels propres 0141 manquants"; exit 3; }
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo "=== build prod (pour --dump-features) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release > "$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass > "$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -30 "$ART/build.log"; exit 5; }

echo "=== dump features (mobilité noir/blanc + balance L/R) sur les positions propres ==="
FEAT="$ART/clean.feat"
./build-prod/jass --dump-features "$CLEAN" "$FEAT" 2>&1 | tail -2

A="--data $CLEAN --skeleton-data $HC --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000"
echo; echo "=== FIT 1 : men-only ==="
python3 pattern_jass/tools/train.py $A --out "$ART/men.pjtw" 2>&1 | tee "$ART/fit-men.log"
echo; echo "=== FIT 2 : men + mobilité/balance ==="
python3 pattern_jass/tools/train.py $A --features-file "$FEAT" --out "$ART/menmob.pjtw" 2>&1 | tee "$ART/fit-menmob.log"
echo; echo "=== FIT 3 : men + king + mobilité/balance (tout l'addable) ==="
python3 pattern_jass/tools/train.py $A --king-features --features-file "$FEAT" --out "$ART/menall.pjtw" 2>&1 | tee "$ART/fit-menall.log"

getmse () { grep -oE 'mse=[0-9.]+' "$1" | head -1 | cut -d= -f2; }
M=$(getmse "$ART/fit-men.log"); MB=$(getmse "$ART/fit-menmob.log"); ALL=$(getmse "$ART/fit-menall.log")
echo; echo "=========================================================="
echo "        0146 DYNAMIC-FEATURES FIT-CHECK — VERDICT"
echo "=========================================================="
echo "  men-only              : val_mse=${M:-?}"
echo "  men + mobilité/balance: val_mse=${MB:-?}"
echo "  men + king + mob/bal  : val_mse=${ALL:-?}"
python3 - "${M:-}" "${MB:-}" "${ALL:-}" <<'PYEOF'
import sys
def f(x):
    try: return float(x)
    except: return None
m,mb,al=map(f,sys.argv[1:4])
def pct(a,b):
    return f"{100*(a-b)/a:+.1f}%" if (a and b) else "n/a"
print()
if m:
    print(f"  → mobilité/balance : {pct(m,mb)}   |   tout addable : {pct(m,al)}")
    best = min([x for x in (mb,al) if x], default=m)
    red = 100*(m-best)/m if m else 0
    print()
    if red>=8:
        print("  → des features ADDABLES (mobilité/balance/king) expliquent une")
        print("    bonne part du résidu → enrichir l'éval pattern (men+ces termes).")
    else:
        print("  → même mobilité+balance+king ne bougent quasi rien le résidu →")
        print("    il est DYNAMIQUE/TACTIQUE profond, qu'aucun pattern statique ne")
        print("    capte → REPIVOT NNUE assumé (il encode ces interactions via la")
        print("    recherche/les couches cachées).")
PYEOF
echo "=========================================================="
