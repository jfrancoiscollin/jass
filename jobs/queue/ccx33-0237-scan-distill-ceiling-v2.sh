#!/usr/bin/env bash
# id: ccx33-0237-scan-distill-ceiling-v2
# description: DATA-SCALING / PLAFOND — teste l'hypothèse "on est data-limited, pas
# geometry-limited". On entraîne notre éval full-fold 32-pat DIRECTEMENT sur les labels
# Scan-d10 (prof. parfaite = limite haute de la qualité de données), sur 1.0M positions,
# et on mesure : proxy vs Scan (held-out), Elo vs hc, Elo vs Scan. Si le proxy explose
# au-dessus du plateau self-play (~0.47) → ce sont les LABELS qui brident la boucle
# (recette = distiller Scan / labels profonds). Si ça reste ~0.5 → c'est la CLASSE d'éval
# qui plafonne (il faudra de la non-linéarité). Comparer à 0235 (self-play vs Scan).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0237-scan-distill-ceiling-v2/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }
SCAN_BIN=/root/jass-scan/scan_linux
# Scan REQUIS : le verdict du plafond = parties réelles vs Scan (sur CCX33, où 0235 l'a validé).
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable à $SCAN_BIN — verdict-parties impossible"; exit 3; }
NTRAIN=1000000        # train split = premiers 1.0M ; proxy = held-out [1.3M, 1.35M)

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns ; master records=$(python3 -c "import struct;print(struct.unpack('<I',open('$MASTER','rb').read(8)[4:8])[0])")"

proxy(){ python3 tools/eval_proxy.py --jass "$JASS" --eval "$1" --testset "$MASTER" \
           --offset 1300000 --max 50000 --score-drop 4900 2>/dev/null | grep -oE 'spearman=[-0-9.]+' | head -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc 9 "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; echo "  (${W:-0}-${D:-0}-${L:-0})" >&2; }

# --- train split = premiers 1.0M (disjoint du proxy tail @1.3M) ; features SUR CE SPLIT ---
MTRAIN="$ART/master1M.jnnw"
python3 - "$MASTER" "$MTRAIN" "$NTRAIN" <<'PYEOF'
import struct,sys
src,dst,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); tot=struct.unpack('<I',b[4:8])[0]; n=min(n,tot); REC=38
o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',n)); o.write(b[8:8+n*REC]); o.close()
print(f"train split {n} of {tot}")
PYEOF
echo "=== dump eval-features sur le split 1M ==="; $JASS --dump-eval-features "$MTRAIN" "$ART/featM" 2>&1 | tail -1

# --- sweep l2 : SÉLECTION PAR VAL-LOSS (perte de régression à Scan held-out, déterministe)
#     — PAS par le proxy. Le verdict est ensuite les PARTIES réelles (vs hc + vs Scan).
#     Le proxy n'est qu'un chiffre secondaire reporté (FYI). ---
BEST_MSE=""; BEST_EVAL=""; BEST_L2=""
for L2 in 3e-4 1e-4 3e-5 1e-5; do
  OUT="$ART/distill-l2$L2.pjtw"
  python3 pattern_jass/tools/train.py --data "$MTRAIN" --scan-eval \
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
RHO=$(proxy "$BEST_EVAL")   # secondaire, FYI uniquement — PAS le critère
echo "MEILLEUR fit (val-loss) : l2=$BEST_L2  val_mse=$BEST_MSE   (proxy FYI=$RHO)"
EHC=$(elo_vs_hc "$BEST_EVAL" 60)
echo "  Elo vs hc (60 paires) = $EHC"

# --- VERDICT : Elo RÉEL vs Scan (fair, sans bitbases, BORNÉ AU TEMPS — pas de depth fixe
#     non plafonné qui ferait exploser le runtime ; mt1s reste comparable à 0235) ---
echo "=== distilled vs Scan (fair, sans bitbases) — LE VERDICT ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$BEST_EVAL" \
    --scan-bb-size 0 --movetime 500 --pairs 3 >"$ART/scan-mt500.log" 2>&1
SELO_MT5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt500.log" | tr '\n' ' ')
echo "  mt0.5s : $SELO_MT5"
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$BEST_EVAL" \
    --scan-bb-size 0 --movetime 1000 --pairs 3 >"$ART/scan-mt.log" 2>&1
SELO_MT=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt.log" | tr '\n' ' ')
echo "  mt1s : $SELO_MT"

echo; echo "=========================================================="
echo "   ccx33-0237 — PLAFOND DE DISTILLATION (classe full-fold 32-pat sur Scan-truth)"
echo "  VERDICT = PARTIES RÉELLES vs Scan (à comparer à 0235, l'éval self-play) :"
echo "    Elo vs Scan @ movetime0.5s : $SELO_MT5"
echo "    Elo vs Scan @ movetime1s   : $SELO_MT   [comparable à 0235 mt1s]"
echo "    Elo vs hc (60 paires)      : $EHC          [self-play gen8 = +142]"
echo "  (secondaire) val_mse=$BEST_MSE  proxy FYI=$RHO  [self-play proxy ~0.47]"
echo "  → distillé NETTEMENT mieux vs Scan que 0235 : DATA/LABEL-limited"
echo "     (recette = distiller Scan / labels profonds dans la boucle)"
echo "  → distillé ≈ 0235 vs Scan (toujours loin) : CLASS-limited (éval non-linéaire requise)"
echo "=========================================================="
