#!/usr/bin/env bash
# id: 0144-phase-split-fitcheck
# description: PRÉ-CHECK phase-split (le pari) — CHEAP, sans parties. Avant
# de câbler l'inférence C++, on teste si phase-split (MG/EG interpolé par le
# nb de pièces) améliore le FIT sur les labels propres de 0141. Si le pattern
# était plombé par la capacité mono-phase, le fit phase-split doit être
# nettement meilleur (val_mse plus bas, sign_acc plus haut). Sinon
# phase-split ne sauvera pas le pattern → on s'épargne le chantier C++.
#
# expected_duration: ~15-30 min (2 fits L-BFGS sur ~1.4M, pas de parties).
set -uo pipefail
cd /root/jass
OUT_BASE="/root/jass/jobs/results/0144-phase-split-fitcheck"; ART="$OUT_BASE/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

# Réutilise les labels PROPRES de 0141 (scan d10 nettoyé) + squelette handcrafted aligné
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
HC=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-hc.jnnw
[ -f "$CLEAN" ] && [ -f "$HC" ] || { echo "ABORT: labels propres de 0141 manquants ($CLEAN / $HC)"; exit 3; }
echo "labels : $CLEAN"; echo "skeleton: $HC"

python3 -c "import numpy, scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

TRAIN_ARGS="--data $CLEAN --skeleton-data $HC --target score --score-clip 5000 --l2 1e-5 --max-iter 200 --scale 1000"

echo; echo "=== FIT 1 : mono-phase (baseline) ==="
python3 pattern_jass/tools/train.py $TRAIN_ARGS --out "$ART/mono.pjtw" 2>&1 | tee "$ART/fit-mono.log"

echo; echo "=== FIT 2 : phase-split (MG/EG) ==="
python3 pattern_jass/tools/train.py $TRAIN_ARGS --phase-split --out "$ART/phase.pjtw" 2>&1 | tee "$ART/fit-phase.log"

# extrait val mse + sign_acc des deux logs
getmse () { grep -oE 'mse=[0-9.]+' "$1" | head -1 | cut -d= -f2; }
getacc () { grep -oE 'sign_acc=[0-9.]+' "$1" | head -1 | cut -d= -f2; }
MSE_M=$(getmse "$ART/fit-mono.log"); ACC_M=$(getacc "$ART/fit-mono.log")
MSE_P=$(getmse "$ART/fit-phase.log"); ACC_P=$(getacc "$ART/fit-phase.log")

echo; echo "=========================================================="
echo "        0144 PHASE-SPLIT FIT-CHECK — VERDICT"
echo "=========================================================="
echo "  mono-phase  : val_mse=${MSE_M:-?}  sign_acc=${ACC_M:-?}"
echo "  phase-split : val_mse=${MSE_P:-?}  sign_acc=${ACC_P:-?}"
python3 - "${MSE_M:-}" "${MSE_P:-}" "${ACC_M:-}" "${ACC_P:-}" <<'EOF'
import sys
def f(x):
    try: return float(x)
    except: return None
mm,mp,am,ap=map(f,sys.argv[1:5])
print()
if mm and mp:
    red = 100*(mm-mp)/mm
    print(f"  → val_mse : {mm:.4f} → {mp:.4f}  ({red:+.1f}%)")
    if am is not None and ap is not None:
        print(f"  → sign_acc: {am:.4f} → {ap:.4f}  ({ap-am:+.4f})")
    print()
    if red >= 8 or (ap and am and ap-am >= 0.02):
        print("  → phase-split AMÉLIORE nettement le fit : la capacité mono-phase")
        print("    était bien un plafond → CÂBLER l'inférence C++ + bencher vs v15.")
    else:
        print("  → fit quasi inchangé : phase-split n'ajoute pas la capacité manquante")
        print("    → ne PAS investir dans l'inférence C++ ; le plafond est ailleurs")
        print("    (features/géométrie 8×12, ou le pattern plafonne vraiment).")
EOF
echo "=========================================================="
