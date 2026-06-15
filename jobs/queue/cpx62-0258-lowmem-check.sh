#!/usr/bin/env bash
# id: cpx62-0258-lowmem-check
# description: ABLATION 2 — isoler la cause RESTANTE de la régression 0254. 0257 a INNOCENTÉ
# phase-weight (sans=+138, avec=+147, tous deux ~80 sous 0241 +229). Restent 2 différences vs
# 0241 : (1) --lowmem (0241 = full-batch) et (2) les DONNÉES de 0254 (les recherches de label
# profondes ont pollué la TT partagée → trajectoires self-play perturbées). Mon test unitaire
# lowmem n'a JAMAIS exercé le chemin --full-fold/--prune → un bug y est plausible. Test décisif :
# ré-entraîner les MÊMES 5.1M en FULL-BATCH (sans --lowmem), Elo vs hc 60p.
#   full-batch ~+229 → BUG --lowmem (impacte tout l'entraînement gros volume → à corriger).
#   full-batch ~+140 → ce sont les DONNÉES de 0254 (perturbation TT par les labels profonds).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0258-lowmem-check/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/cpx62-0254-densify-endgame/artefacts.src
CUM="$SRC/cumulative.jnnw"; FEAT="$SRC/feat8"
[ -f "$CUM" ] && [ -f "$FEAT" ] || { echo "ABORT: data de 0254 introuvable (box recyclée ?)"; exit 3; }
echo "data: $(python3 -c "import struct;print(struct.unpack('<I',open('$CUM','rb').read(8)[4:8])[0])") positions (réutilisées de 0254)"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
val_mse(){ grep -oE 'mse=[0-9.]+' "$1-train.log" | tail -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc 9 "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}

# FULL-BATCH (sans --lowmem), sans phase-weight — sinon STRICTEMENT comme 0241/0257-A.
echo "=== ré-entraînement FULL-BATCH (sans --lowmem) sur les 5.1M de 0254 ==="
python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --eval-features-file "$FEAT" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --full-fold --king-patterns \
    --out "$ART/fullbatch.pjtw" >"$ART/fullbatch-train.log" 2>&1
if [ ! -f "$ART/fullbatch.pjtw" ]; then
  echo "TRAIN FULL-BATCH a échoué (OOM probable à 5.1M ?) :"; tail -12 "$ART/fullbatch-train.log"; exit 7
fi
FB_ELO=$(elo_vs_hc "$ART/fullbatch.pjtw" 60)

echo; echo "=========================================================="
echo "   cpx62-0258 — LOWMEM vs FULL-BATCH (mêmes 5.1M de 0254, Elo vs hc 60p)"
echo "----------------------------------------------------------"
echo "  FULL-BATCH (sans lowmem) : val_mse=$(val_mse "$ART/fullbatch")  val_endgame=$(val_endgame "$ART/fullbatch")  Elo_vs_hc=$FB_ELO"
echo "  (rappels : 0257-A lowmem sans-PW = +138.1 ; 0241 full-batch baseline = +229.5)"
echo "----------------------------------------------------------"
echo "  FULL-BATCH ~+229 (>> +138) → BUG --lowmem sur le chemin full-fold/prune (à corriger,"
echo "     impacte tout entraînement gros volume) ; refaire la densif en full-batch ou lowmem-fixé."
echo "  FULL-BATCH ~+140 (~ lowmem) → ce sont les DONNÉES de 0254 (perturbation TT par les labels"
echo "     profonds) ; régénérer SANS --label-depth-by-phase, lowmem est OK."
echo "=========================================================="
