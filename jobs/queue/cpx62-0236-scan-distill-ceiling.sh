#!/usr/bin/env bash
# id: cpx62-0236-scan-distill-ceiling
# description: DATA-SCALING / PLAFOND — teste l'hypothèse "on est data-limited, pas
# geometry-limited". On entraîne notre éval full-fold 32-pat DIRECTEMENT sur les labels
# Scan-d10 (prof. parfaite = limite haute de la qualité de données), sur 1.0M positions,
# et on mesure : proxy vs Scan (held-out), Elo vs hc, Elo vs Scan. Si le proxy explose
# au-dessus du plateau self-play (~0.47) → ce sont les LABELS qui brident la boucle
# (recette = distiller Scan / labels profonds). Si ça reste ~0.5 → c'est la CLASSE d'éval
# qui plafonne (il faudra de la non-linéarité). Comparer à 0235 (self-play vs Scan).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0236-scan-distill-ceiling/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }
SCAN_BIN=/root/jass-scan/scan_linux
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

echo "=== dump eval-features sur le master ==="; $JASS --dump-eval-features "$MASTER" "$ART/featM" 2>&1 | tail -1

# --- petit sweep l2 : on cherche le PLAFOND (meilleur proxy) de la classe full-fold sur Scan-truth ---
BEST_RHO=-1; BEST_EVAL=""
for L2 in 3e-4 1e-4 3e-5 1e-5; do
  OUT="$ART/distill-l2$L2.pjtw"
  python3 pattern_jass/tools/train.py --data "$MASTER" --max-records "$NTRAIN" --scan-eval \
      --eval-features-file "$ART/featM" --loss logistic --l2 "$L2" --max-iter 300 --scale 1000 \
      --prune --full-fold --out "$OUT" >"$ART/train-l2$L2.log" 2>&1
  if [ -f "$OUT" ]; then RHO=$(proxy "$OUT"); echo "  l2=$L2  proxy(vs Scan held-out)=$RHO"
    awk -v r="${RHO:-0}" -v b="$BEST_RHO" 'BEGIN{exit !(r>b)}' && { BEST_RHO="$RHO"; BEST_EVAL="$OUT"; }
  else echo "  l2=$L2  TRAIN FAIL"; tail -3 "$ART/train-l2$L2.log"; fi
done
[ -n "$BEST_EVAL" ] || { echo "ABORT: aucune distillation entraînée"; exit 7; }
echo "MEILLEUR plafond : proxy=$BEST_RHO  ($BEST_EVAL)"
EHC=$(elo_vs_hc "$BEST_EVAL" 60)
echo "  Elo vs hc (60 paires) = $EHC"

# --- optionnel : Elo RÉEL vs Scan (si binaire présent) — directement comparable à 0235 ---
SELO_D9="(skipped)"; SELO_MT="(skipped)"
if [ -x "$SCAN_BIN" ]; then
  echo "=== distilled vs Scan (fair, sans bitbases) ==="
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$BEST_EVAL" \
      --scan-bb-size 0 --depth 9 --pairs 24 >"$ART/scan-d9.log" 2>&1
  SELO_D9=$(grep -E 'score rate|ELO estimate' "$ART/scan-d9.log" | tr '\n' ' ')
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$BEST_EVAL" \
      --scan-bb-size 0 --movetime 1000 --pairs 24 >"$ART/scan-mt.log" 2>&1
  SELO_MT=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt.log" | tr '\n' ' ')
else echo "  (Scan absent — Elo vs Scan sauté ; proxy + Elo vs hc suffisent pour le plafond)"; fi

echo; echo "=========================================================="
echo "   cpx62-0236 — PLAFOND DE DISTILLATION (classe full-fold 32-pat sur Scan-truth)"
echo "  proxy vs Scan (plafond)     : $BEST_RHO    [self-play plafonnait ~0.47]"
echo "  Elo vs hc (eval distillé)   : $EHC          [self-play gen8 = +142]"
echo "  Elo vs Scan @ depth9        : $SELO_D9"
echo "  Elo vs Scan @ movetime1s    : $SELO_MT"
echo "  → proxy >> 0.47  : on est DATA/LABEL-limited (recette = distiller Scan / labels profonds)"
echo "  → proxy ~ 0.5    : on est CLASS-limited (il faut une éval non-linéaire)"
echo "=========================================================="
