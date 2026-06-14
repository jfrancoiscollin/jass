#!/usr/bin/env bash
# id: cpx62-0251-phase-ceiling
# description: DIAGNOSTIC FINALES 1/2 — PLAFOND DE LA CLASSE, PAR PHASE. Les autopsies
# 0249/0250 montrent une éval QUASI-Scan en ouverture/milieu (perte ~0.05) qui SAIGNE en
# finale (perte ~2.8, ×50), surtout avec rois. Question : est-ce la CLASSE LINÉAIRE qui ne
# sait pas représenter la finale, ou la DONNÉE (famine de finales) ? On distille la classe
# KING-AWARE (notre championne, cf 0241/0250) DIRECTEMENT sur les labels Scan-d10 parfaits
# (1.0M), on choisit le l2 par VAL-LOSS (pas le proxy retiré), puis on mesure l'accord
# STATIQUE par phase (tools/phase_proxy.py) sur le tail held-out [1.3M, 1.42M).
#   * spearman s'effondre / RMSE explose dans les buckets finale  -> CLASSE-limited en finale
#     (même avec labels parfaits la classe ne tient pas : c'est un plafond de classe).
#   * spearman reste haut partout -> la classe TIENT en finale ; le saignement en partie
#     (0249/0250) vient de la DONNÉE (famine) ou de la recherche (cf diag 2/2 = ccx33-0252).
# La distribution des labels par bucket quantifie la famine elle-même (combien de finales).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0251-phase-ceiling/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }
NTRAIN=1000000        # train = premiers 1.0M ; mesure phase = held-out tail [1.3M, fin)

# --- build KING-AWARE jass (la classe championne ; .pjtw porteront le bit KING) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: build pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns (king-aware) ; master=$(python3 -c "import struct;print(struct.unpack('<I',open('$MASTER','rb').read(8)[4:8])[0])")"

# --- train split = premiers 1.0M (disjoint du tail held-out @1.3M) ---
MTRAIN="$ART/master1M.jnnw"
python3 - "$MASTER" "$MTRAIN" "$NTRAIN" <<'PYEOF'
import struct,sys
src,dst,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; n=min(n,tot); REC=38
o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',n)); o.write(b[8:8+n*REC]); o.close()
print(f"train split {n} of {tot}")
PYEOF
echo "=== dump eval-features (extras, occupancy-independant) sur le split 1M ==="
$JASS --dump-eval-features "$MTRAIN" "$ART/featM" 2>&1 | tail -1

# --- sweep l2, SÉLECTION PAR VAL-LOSS (mse held-out interne au trainer), KING-AWARE ---
BEST_MSE=""; BEST_EVAL=""; BEST_L2=""
for L2 in 3e-4 1e-4 3e-5 1e-5; do
  OUT="$ART/distill-king-l2$L2.pjtw"
  python3 pattern_jass/tools/train.py --data "$MTRAIN" --scan-eval --king-patterns \
      --eval-features-file "$ART/featM" --loss logistic --l2 "$L2" --max-iter 300 --scale 1000 \
      --prune --full-fold --out "$OUT" >"$ART/train-l2$L2.log" 2>&1
  if [ -f "$OUT" ]; then
    MSE=$(grep -oE 'mse=[0-9.]+' "$ART/train-l2$L2.log" | tail -1 | cut -d= -f2)
    echo "  l2=$L2  val_mse=${MSE:-NA}"
    if [ -n "$MSE" ] && { [ -z "$BEST_MSE" ] || awk -v m="$MSE" -v b="$BEST_MSE" 'BEGIN{exit !(m<b)}'; }; then
      BEST_MSE="$MSE"; BEST_EVAL="$OUT"; BEST_L2="$L2"; fi
  else echo "  l2=$L2  TRAIN FAIL"; tail -3 "$ART/train-l2$L2.log"; fi
done
[ -n "$BEST_EVAL" ] || { echo "ABORT: aucune distillation entraînée"; exit 7; }
echo "MEILLEUR fit (val-loss) : l2=$BEST_L2  val_mse=$BEST_MSE  -> $BEST_EVAL"

# --- MESURE : accord statique PAR PHASE sur le tail held-out [1.3M, fin) ---
echo "=== phase_proxy : accord éval-distillée vs Scan-d10, par phase (tail held-out) ==="
python3 tools/phase_proxy.py --jass "$JASS" --eval "$BEST_EVAL" --testset "$MASTER" \
    --offset 1300000 --max 0 --score-drop 4900 --out "$ART/phase-ceiling.txt" 2>"$ART/phase.err" \
  || { echo "ABORT: phase_proxy a échoué"; tail -10 "$ART/phase.err"; exit 8; }

echo; echo "=========================================================="
echo "   cpx62-0251 — PLAFOND DE CLASSE PAR PHASE (distillé king-aware sur Scan-truth)"
echo "   l2 retenu (val-loss) = $BEST_L2  val_mse=$BEST_MSE"
echo "----------------------------------------------------------"
cat "$ART/phase-ceiling.txt"
echo "=========================================================="
echo "  À CROISER avec l'autopsie 0250 (king-aware en partie) : si la classe RANGE bien"
echo "  les finales ici (spearman haut) mais saigne en partie -> donnée/recherche, pas classe."
echo "=========================================================="
