#!/usr/bin/env bash
# id: 0145-king-features-fitcheck
# description: PRÉ-CHECK "pattern plus riche" — phase-split réfuté (0144), on
# teste l'hypothèse la plus probable : le pattern est AVEUGLE AUX ROIS
# (men-only), or le résidu Scan−handcrafted dépend sûrement des rois. On
# ajoute 100 features king-PST au fit et on regarde si le val_mse chute.
# Cheap, sans parties.
#   - Fit nettement meilleur → l'info ROI manquait → richer pattern king-aware vaut le coup.
#   - Fit quasi inchangé → le résidu est ailleurs (dynamique/tactique) → repivot.
# expected_duration: ~15-30 min (2 fits).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0145-king-features-fitcheck"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname) ==="
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
HC=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-hc.jnnw
[ -f "$CLEAN" ] && [ -f "$HC" ] || { echo "ABORT: labels propres 0141 manquants"; exit 3; }
python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
A="--data $CLEAN --skeleton-data $HC --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000"

echo; echo "=== FIT 1 : men-only (baseline) ==="
python3 pattern_jass/tools/train.py $A --out "$ART/men.pjtw" 2>&1 | tee "$ART/fit-men.log"
echo; echo "=== FIT 2 : men + king-features (king-PST) ==="
python3 pattern_jass/tools/train.py $A --king-features --out "$ART/menking.pjtw" 2>&1 | tee "$ART/fit-menking.log"

getmse () { grep -oE 'mse=[0-9.]+' "$1" | head -1 | cut -d= -f2; }
M=$(getmse "$ART/fit-men.log"); K=$(getmse "$ART/fit-menking.log")
echo; echo "=========================================================="
echo "        0145 KING-FEATURES FIT-CHECK — VERDICT"
echo "=========================================================="
echo "  men-only       : val_mse=${M:-?}"
echo "  men + king-PST : val_mse=${K:-?}"
python3 - "${M:-}" "${K:-}" <<'PYEOF'
import sys
def f(x):
    try: return float(x)
    except: return None
m,k=map(f,sys.argv[1:3])
if m and k:
    red=100*(m-k)/m
    print(f"  → val_mse : {m:.4f} → {k:.4f}  ({red:+.1f}%)")
    print()
    if red>=8:
        print("  → les ROIS portaient une grosse part du résidu → richer pattern")
        print("    king-aware vaut le coup (king-PST/patterns-rois) → on l'implémente.")
    else:
        print("  → king-PST n'aide quasi pas → le résidu est dans le DYNAMIQUE")
        print("    (mobilité/tactique) qu'aucun pattern statique simple ne capte → repivot NNUE.")
PYEOF
echo "=========================================================="
