#!/usr/bin/env bash
# id: 0199-reanchor-champion-vs-scan
# description: RÉ-ANCRAGE. Angle mort : on benche tout contre v15, qui fait
# ~0.05 vs Scan à profondeur égale (0197). Le champion fait 0.39 *contre v15*
# — mais ça peut valoir n'importe quoi contre Scan, la vraie référence. Tant
# qu'on n'a pas champion-vs-Scan, aucun chiffre n'est interprétable en absolu,
# et on ne sait pas si un relabel profond (étape 6) vaut le coup.
#
# On mesure donc, MÊME instrument que 0197 (harness corrigé, no bitbases) :
#   * champion (pattern, distill Scan-d10) vs Scan à profondeur égale {7,9,11}
#   * v15 (NNUE) vs Scan aux mêmes profondeurs (side-by-side propre, même
#     install Scan — re-confirme les 0.028/0.056/0.056 de 0197)
#   * champion vs Scan au movetime 0.5s (north-star ; rappel v15 mt = 0.019)
#
#   Lecture : champion ≫ v15 vs Scan → notre pattern-eval est bien plus proche
#   que v15 ne le suggérait, le relabel profond linéaire vaut le coup.
#   champion ≈ v15 (~0.05) vs Scan → même notre meilleure eval est loin, le
#   problème éval est grand ouvert (et le plafond linéaire se pose vraiment).
#
# expected_duration: ~40 min (build + Scan + 6 matchs depth courts + 1 mt).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/0199-reanchor-champion-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
echo "=== host : $(hostname)  nproc=$NCPU ==="

# --- build ----------------------------------------------------------------
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass

# --- Scan -----------------------------------------------------------------
SCAN_DIR=/root/jass/.scan
if [ ! -x "$SCAN_DIR/scan_linux" ]; then
    echo "=== installing Scan (rhalbersma/scan) ==="
    rm -rf "$SCAN_DIR"
    git clone --depth 1 https://github.com/rhalbersma/scan "$SCAN_DIR" || { echo "ABORT: clone scan"; exit 4; }
    chmod +x "$SCAN_DIR/scan_linux"
fi
SCAN="$SCAN_DIR/scan_linux"; [ -x "$SCAN" ] || { echo "ABORT: scan"; exit 4; }

# --- v15 + champion -------------------------------------------------------
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
CHAMP=/root/jass/jobs/results/0196-selfplay-wdl-1M/artefacts.src/champ.pjtw
if [ ! -f "$CHAMP" ]; then
  echo "=== champ.pjtw de 0196 absent → re-distill (recette champion) ==="
  CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
  [ -f "$CLEAN" ] || { echo "ABORT: master clean introuvable pour re-distill"; exit 3; }
  ./build-prod/jass --dump-eval-features "$CLEAN" "$ART/champ.feat" 2>&1 | tail -1
  python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/champ.feat" \
    --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
    --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/champ.pjtw" >"$ART/champ-train.log" 2>&1
  CHAMP="$ART/champ.pjtw"; [ -f "$CHAMP" ] || { echo "ABORT: re-distill champion"; exit 7; }
  rm -f "$ART/champ.feat"
fi
echo "v15      : $V15"
echo "champion : $CHAMP"

jrate(){ grep -oE 'Jass score rate:\s*[0-9.]+' "$1" 2>/dev/null | grep -oE '[0-9.]+' | head -1; }
match(){ # $1=tag  $2..=calibrate args
  local tag="$1"; shift
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN" --jass-threads 1 "$@" >"$ART/$tag.log" 2>&1
  echo "$(jrate "$ART/$tag.log")"; }

# --- profondeur égale {7,9,11} : champion ET v15 vs Scan ------------------
echo; echo "############ profondeur égale vs Scan (FAIR, no bitbases) ############"
for D in 7 9 11; do
  r_ch=$(match "champ-d$D" --jass-pattern "$CHAMP" --depth "$D" --pairs 8)
  r_v1=$(match "v15-d$D"   --nnue        "$V15"   --depth "$D" --pairs 8)
  echo "  depth $D : champion=$r_ch   v15=$r_v1"
done

# --- movetime 0.5s : champion vs Scan (north-star) ------------------------
echo; echo "############ movetime 0.5s vs Scan (north-star) ############"
r_mt=$(match "champ-mt500" --jass-pattern "$CHAMP" --movetime 0.5 --pairs 4)
echo "  champion mt=0.5s vs Scan = $r_mt"

echo; echo "=========================================================="
echo "   0199 RÉ-ANCRAGE champion vs Scan — VERDICT"
echo "  profondeur égale vs Scan :"
for D in 7 9 11; do echo "    depth $D : champion=$(jrate "$ART/champ-d$D.log")   v15=$(jrate "$ART/v15-d$D.log")"; done
echo "  movetime 0.5s : champion=$(jrate "$ART/champ-mt500.log")   (rappel v15 mt = 0.019, 0137)"
echo "  RAPPEL 0197 : v15 vs Scan depth 7/9/11 = 0.028 / 0.056 / 0.056"
echo "  → champion ≫ v15 vs Scan = pattern-eval bien plus proche → relabel profond linéaire vaut le coup (étape 6)."
echo "  → champion ≈ v15 (~0.05) = même la meilleure eval est loin → plafond linéaire à reposer (NNUE/features)."
echo "=========================================================="
