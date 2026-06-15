#!/usr/bin/env bash
# id: cpx62-0260-endgame-distill
# description: DENSIFICATION FINALE — CHEMIN CORRIGÉ (distillation sur SCORE, pas WDL).
# Apprentissage clé de 0254/0257/0258 : la boucle self-play s'entraîne sur le WDL (résultat),
# dont les labels de FINALE sont BRUITÉS (play depth-4 juge mal) → --phase-weight les amplifie
# et NUIT. Ici on distille la classe KING-AWARE sur les SCORES Scan-d10 PARFAITS du master
# (--target score, PAS --loss logistic), où les labels de finale sont BONS → --phase-weight
# DOIT aider. 0251 a montré que la classe range la finale à spearman 0.79 sur ces labels.
# On entraîne AVEC et SANS phase-weight (contrôle) pour ISOLER son effet sur de BONS labels :
#   val_endgame_mse baisse AVEC sans casser l'ouverture → le levier marche sur bons labels.
# Sélection par val-loss (sweep l2). Verdict = Elo vs hc 60p + vs Scan mt0.5 ; val/phase mse.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0260-endgame-distill/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master Scan-d10 introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "master=$(python3 -c "import struct;print(struct.unpack('<I',open('$MASTER','rb').read(8)[4:8])[0])") positions Scan-d10"

echo "=== dump eval-features (extras) sur le master ==="
$JASS --dump-eval-features "$MASTER" "$ART/featM" 2>&1 | tail -1

val_endgame(){ grep -oE 'val/phase mse : .*' "$1" | grep -oE 'endgame=[0-9.]+' | head -1 | cut -d= -f2; }
val_mse(){ grep -oE 'mse=[0-9.]+' "$1" | tail -1 | cut -d= -f2; }
elo_vs_hc(){ local lg="$ART/elo-$(basename "$1" .pjtw).log"
  $JASS --benchmark-scan-eval "$1" hc 9 "$2" "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  echo "${W:-0}-${D:-0}-${L:-0} elo=$(python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)"
}
# distille SCORE (LS), king-aware full-fold ; $1=tag $2=phase-weight-arg(ou vide)
distill(){ local tag="$1"; shift
  local best=""; local bmse=""; local bl2=""
  for L2 in 3e-4 1e-4; do
    local out="$ART/$tag-l2$L2.pjtw"; local log="$ART/$tag-l2$L2-train.log"
    python3 pattern_jass/tools/train.py --data "$MASTER" --scan-eval --king-patterns \
        --eval-features-file "$ART/featM" --target score --score-clip 2000 --score-drop 4900 \
        --l2 "$L2" --max-iter 300 --scale 1000 --prune --full-fold "$@" --out "$out" >"$log" 2>&1
    if [ -f "$out" ]; then
      local m=$(val_mse "$log"); echo "  [$tag] l2=$L2 val_mse=${m:-NA}"
      if [ -n "$m" ] && { [ -z "$bmse" ] || awk -v a="$m" -v b="$bmse" 'BEGIN{exit !(a<b)}'; }; then bmse="$m"; best="$out"; bl2="$L2"; fi
    else echo "  [$tag] l2=$L2 TRAIN FAIL"; tail -4 "$log"; fi
  done
  echo "$best|$bl2|$bmse"
}

echo "=== A : distillation SCORE SANS phase-weight (contrôle) ==="
A=$(distill noPW); A_EVAL=$(echo "$A"|cut -d'|' -f1); A_L2=$(echo "$A"|cut -d'|' -f2)
echo "=== B : distillation SCORE AVEC phase-weight endgame=3,deep-eg=3 ==="
B=$(distill withPW --phase-weight "endgame=3,deep-eg=3"); B_EVAL=$(echo "$B"|cut -d'|' -f1); B_L2=$(echo "$B"|cut -d'|' -f2)
[ -n "$A_EVAL" ] && [ -n "$B_EVAL" ] || { echo "ABORT: distillation échouée"; exit 7; }

A_ENDG=$(val_endgame "${A_EVAL%.pjtw}-train.log"); B_ENDG=$(val_endgame "${B_EVAL%.pjtw}-train.log")
A_ELO=$(elo_vs_hc "$A_EVAL" 60); B_ELO=$(elo_vs_hc "$B_EVAL" 60)

# --- vs Scan (mt0.5) pour la meilleure des deux (Elo vs hc) ---
BETTER="$A_EVAL"; case "$A_ELO $B_ELO" in *) :;; esac
awk -v a="$(echo "$A_ELO"|grep -oE 'elo=[-+0-9.]+'|cut -d= -f2)" -v b="$(echo "$B_ELO"|grep -oE 'elo=[-+0-9.]+'|cut -d= -f2)" 'BEGIN{exit !(b>a)}' && BETTER="$B_EVAL"
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || echo "(clone Scan échoué)"
  chmod +x "$SCAN_BIN" 2>/dev/null || true
fi
SCAN5=""
[ -x "$SCAN_BIN" ] && { python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
    --jass-pattern "$BETTER" --scan-bb-size 0 --movetime 0.5 --pairs 3 >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' '); }

echo; echo "=========================================================="
echo "   cpx62-0260 — DISTILLATION FINALE SUR SCORE (king-aware, Scan-d10)"
echo "----------------------------------------------------------"
echo "  A SANS phase-weight : l2=$A_L2  val_endgame_mse=$A_ENDG  Elo_vs_hc=$A_ELO"
echo "  B AVEC phase-weight : l2=$B_L2  val_endgame_mse=$B_ENDG  Elo_vs_hc=$B_ELO"
echo "  meilleure vs Scan mt0.5 : ${SCAN5:-(Scan indispo)}"
echo "  (rappels : self-play 0241 +229 vs hc ; distill-WDL 0237 +90.8)"
echo "----------------------------------------------------------"
echo "  B val_endgame_mse < A SANS casser l'Elo global → phase-weight MARCHE sur bons labels"
echo "  (≠ WDL self-play où il nuisait). Si distill score >> distill-WDL 0237 → le SCORE est"
echo "  le bon signal de finale. Étape suivante probable : BLENDER self-play (force globale) +"
echo "  distill-finale (anti-forget anchor) pour cumuler force d'ouverture ET qualité de finale."
echo "=========================================================="
