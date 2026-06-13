#!/usr/bin/env bash
# id: cpx62-0216-sprt-b4
# description: Nœud 2ter·B4 — le mur ~0.46 est-il RÉEL ou un artefact du PROXY ? Le proxy
# mesure l'accord-SCORE statique avec Scan-d10 ; un eval WDL peut plafonner là en accord
# tout en gagnant des PARTIES. Test en parties RÉELLES de la boucle profondeur cpx62-0214
# (evals locaux, non committés mais survivants en artefacts.src) :
#   (1) gen0 (seed) vs handcrafted  ET  genBest vs handcrafted, même profondeur → l'Elo
#       RÉEL gagné par la boucle (gen0→best). Si grand alors que le proxy bouge peu
#       (0.40→0.46) ⇒ le proxy SOUS-LIT la force ⇒ on n'était pas muré, on SCALE.
#       Si ~0 ⇒ pas de gain réel ⇒ le mur est réel ⇒ Nœud 3 (classe).
#   (2) (best-effort) genBest vs SCAN à profondeur égale → l'écart ABSOLU à Scan.
# Tourne APRÈS 0214 (même box CPX62 → lit ses evals locaux). SPRT/Elo via tools/sprt_elo.py.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0216-sprt-b4/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SRC=/root/jass/jobs/results/cpx62-0214-depth-mt30/artefacts.src
[ -f "$SRC/gen0.pjtw" ] || { echo "ABORT: cpx62-0214 seed introuvable ($SRC) — 0214 a-t-il tourné ici ?"; exit 3; }
SEED="$SRC/gen0.pjtw"; BEST=""
for g in 5 4 3 2 1; do [ -f "$SRC/gen$g.pjtw" ] && { BEST="$SRC/gen$g.pjtw"; BESTG=$g; break; }; done
[ -n "$BEST" ] || { echo "ABORT: aucun gen<N>.pjtw dans 0214"; exit 3; }
echo "B4 : SEED=gen0  BEST=gen$BESTG"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy

DEPTH=9; PAIRS=80; TH=8     # 80 pairs = 160 games per matchup ; 8 search threads
wdl_from_bench(){ # <logfile> → "W D L" (SCAN_EVAL=W NNUE=L Draws=D)
  local f="$1"
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$f" | tail -1 | cut -d= -f2)
  local L=$(grep -oE 'NNUE=[0-9]+'      "$f" | tail -1 | cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+'     "$f" | tail -1 | cut -d= -f2)
  echo "${W:-0} ${D:-0} ${L:-0}"
}

# --- (1) vs handcrafted (self-contained, no Scan) : seed & best in PARALLEL ---
echo "=== (1) gen0 vs hc  &  gen$BESTG vs hc  (depth $DEPTH, $PAIRS pairs, $TH threads) ==="
$JASS --benchmark-scan-eval "$SEED" hc "$DEPTH" "$PAIRS" "$TH" 0 >"$ART/seed-hc.log" 2>&1 &
$JASS --benchmark-scan-eval "$BEST" hc "$DEPTH" "$PAIRS" "$TH" 0 >"$ART/best-hc.log" 2>&1 &
wait
read sW sD sL <<<"$(wdl_from_bench "$ART/seed-hc.log")"
read bW bD bL <<<"$(wdl_from_bench "$ART/best-hc.log")"
echo "  gen0  vs hc : W=$sW D=$sD L=$sL"; python3 tools/sprt_elo.py --wdl "$sW" "$sD" "$sL" | sed 's/^/    /'
echo "  gen$BESTG vs hc : W=$bW D=$bD L=$bL"; python3 tools/sprt_elo.py --wdl "$bW" "$bD" "$bL" | sed 's/^/    /'

# --- (2) best-effort : genBest vs SCAN at equal depth (absolute gap) ---
echo "=== (2) gen$BESTG vs Scan (best-effort, equal depth $DEPTH) ==="
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
  rm -rf "$SCAN_DIR"; git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" 2>"$ART/scan-clone.log" \
    && chmod +x "$SCAN_DIR/scan_linux" 2>/dev/null || echo "  (scan clone failed — réseau ? on saute le vs-Scan)"
fi
if [ -x "$SCAN_DIR/scan_linux" ]; then
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_DIR/scan_linux" \
    --jass-pattern "$BEST" --depth "$DEPTH" --pairs 60 --scan-book off --scan-bb-size 0 \
    >"$ART/best-vs-scan.log" 2>&1 || echo "  (calibrate a échoué — voir best-vs-scan.log)"
  cW=$(grep -oE 'Jass=[0-9]+'  "$ART/best-vs-scan.log" | tail -1 | cut -d= -f2)
  cL=$(grep -oE 'Scan=[0-9]+'  "$ART/best-vs-scan.log" | tail -1 | cut -d= -f2)
  cD=$(grep -oE 'Draws=[0-9]+' "$ART/best-vs-scan.log" | tail -1 | cut -d= -f2)
  if [ -n "$cW" ]; then
    echo "  gen$BESTG vs Scan : W=$cW D=$cD L=$cL"; python3 tools/sprt_elo.py --wdl "$cW" "$cD" "$cL" | sed 's/^/    /'
  else echo "  (pas de résultat vs-Scan parsable)"; tail -5 "$ART/best-vs-scan.log"; fi
fi

echo; echo "=========================================================="
echo "   cpx62-0216 — B4 : le mur ~0.46 est-il RÉEL ?  (parties réelles)"
echo "  Elo RÉEL gagné par la boucle (gen0→gen$BESTG, vs hc commun) :"
echo "    gen0  vs hc : $sW-$sD-$sL   |   gen$BESTG vs hc : $bW-$bD-$bL"
echo "  → si gen$BESTG ≫ gen0 en Elo alors que le proxy bouge peu (0.40→0.46) :"
echo "    le PROXY SOUS-LIT la force → on n'est PAS muré → SCALER (data+profondeur+2-box)."
echo "  → si gen$BESTG ≈ gen0 : pas de gain réel → mur RÉEL → Nœud 3 (géométrie/FM/non-lin)."
echo "  (2) écart absolu à Scan ci-dessus = à combien d'Elo on est de la cible."
echo "=========================================================="
