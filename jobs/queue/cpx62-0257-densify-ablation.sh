#!/usr/bin/env bash
# id: cpx62-0257-densify-ablation
# description: ABLATION — isoler la cause de la régression 0254 (densifié +149.5 vs baseline
# 0241 +229.5, val_endgame_mse MONTÉ). Hypothèse : la boucle s'entraîne sur le WDL (résultat
# de partie), donc (a) --label-depth-by-phase est un no-op (n'affecte que le champ score,
# inutilisé) et (b) --phase-weight a AMPLIFIÉ des labels WDL de finale BRUITÉS (self-play
# depth-4 juge mal les finales) → dégradation. Test PEU CHER : on RÉUTILISE les 5.1M déjà
# générés par 0254 (cumulative.jnnw + feat8, sur le disque de la box) et on ré-entraîne DEUX
# évals — SANS et AVEC phase-weight — toutes choses égales par ailleurs, Elo vs hc 60p chacune.
#   SANS phase-weight remonte ~+229 → phase-weight EST le coupable (CQFD).
#   SANS reste ~+149 → ce n'est pas phase-weight (creuser lowmem/données).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0257-densify-ablation/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/cpx62-0254-densify-endgame/artefacts.src
CUM="$SRC/cumulative.jnnw"; FEAT="$SRC/feat8"
[ -f "$CUM" ]  || { echo "ABORT: cumulative.jnnw de 0254 introuvable (box recyclée ?)"; exit 3; }
[ -f "$FEAT" ] || { echo "ABORT: feat8 de 0254 introuvable"; exit 3; }
echo "data: $(python3 -c "import struct;print(struct.unpack('<I',open('$CUM','rb').read(8)[4:8])[0])") positions (réutilisées de 0254)"

# --- build KING-AWARE (= l'éval de 0254) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

CFOLD="--full-fold --king-patterns"
val_endgame(){ grep -oE 'val/phase mse : .*' "$1-train.log" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
val_mse(){ grep -oE 'mse=[0-9.]+' "$1-train.log" | tail -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc 9 "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}

# A = SANS phase-weight (contrôle) ; B = AVEC (repro de gen8). Même data, même l2.
echo "=== A : ré-entraînement SANS phase-weight (contrôle) ==="
python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --eval-features-file "$FEAT" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD \
    --out "$ART/noPW.pjtw" >"$ART/noPW-train.log" 2>&1
[ -f "$ART/noPW.pjtw" ] || { echo "ABORT train A"; tail -8 "$ART/noPW-train.log"; exit 7; }
A_ELO=$(elo_vs_hc "$ART/noPW.pjtw" 60)

echo "=== B : ré-entraînement AVEC phase-weight endgame=3,deep-eg=3 (repro) ==="
python3 pattern_jass/tools/train.py --data "$CUM" --scan-eval --eval-features-file "$FEAT" \
    --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --lowmem $CFOLD \
    --phase-weight "endgame=3,deep-eg=3" --out "$ART/withPW.pjtw" >"$ART/withPW-train.log" 2>&1
[ -f "$ART/withPW.pjtw" ] || { echo "ABORT train B"; tail -8 "$ART/withPW-train.log"; exit 7; }
B_ELO=$(elo_vs_hc "$ART/withPW.pjtw" 60)

echo; echo "=========================================================="
echo "   cpx62-0257 — ABLATION phase-weight (mêmes 5.1M de 0254, Elo vs hc 60p)"
echo "----------------------------------------------------------"
echo "  A  SANS phase-weight : val_mse=$(val_mse "$ART/noPW")  val_endgame=$(val_endgame "$ART/noPW")  Elo_vs_hc=$A_ELO"
echo "  B  AVEC phase-weight : val_mse=$(val_mse "$ART/withPW")  val_endgame=$(val_endgame "$ART/withPW")  Elo_vs_hc=$B_ELO"
echo "  (rappels : 0241 baseline +229.5 ; 0254 gen8 densifié +149.5)"
echo "----------------------------------------------------------"
echo "  A ~+229 & A >> B → phase-weight EST le coupable (sur-pondère du WDL de finale bruité)."
echo "  A ~+149 ~ B      → ce n'est pas phase-weight ; creuser lowmem/données/build."
echo "  → corrige le chemin : densif finale par DISTILLATION sur SCORE (deep/Scan-d10), pas WDL+poids."
echo "=========================================================="
