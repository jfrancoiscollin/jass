#!/usr/bin/env bash
# id: 0189-nps-gap-profile
# description: PROFILAGE DU ×6 — Scan (même archi, plus simple) ≈ ×8 NPS vs v15 et
# le pulvérise au movetime ; nous on n'est qu'à ×1.3 (0178). Donc ~×6 de vitesse
# perdus = c'est un problème d'IMPLÉMENTATION, pas de connaissance. perf n'est pas
# installé sur le runner → on attribue le ×6 par A/B de débit :
#
#   (1) DÉBIT ÉVAL brut (--bench-eval, evals/s) : scan-eval v4 vs v15. Notre éval
#       linéaire DEVRAIT pulvériser le NNUE par appel. Si ≈/< v15 → l'éval est le
#       problème (compute_extras recalculé/non-incrémental, etc.).
#   (2) NPS de RECHERCHE (depth-at-movetime knps) : jass+scan-eval vs jass+hc vs
#       v15. hc >> scan-eval → l'éval draine la recherche. hc ≈ scan-eval mais
#       tous << Scan → le goulot est movegen/make-unmake (cœur moteur).
#   (3) NPS de SCAN (cible, best-effort) → confirme le ×8.
#
# expected_duration: ~30-45 min.
set -uo pipefail
cd /root/jass; ART="/root/jass/jobs/results/0189-nps-gap-profile/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
CLEAN=/root/jass/jobs/results/0141-pattern-reeval/artefacts.src/master-clean-scan-d10.jnnw
[ -f "$CLEAN" ] || { echo ABORT; exit 3; }
V15=$(find /root/jass/jobs/results -path '*128-64*' -name 'nnue-*-q.bin' 2>/dev/null | head -1)
[ -f "$V15" ] || { echo ABORT v15; exit 3; }
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
./build-prod/jass_tests >"$ART/tests.log" 2>&1 && echo "tests OK" || { echo TESTS FAIL; exit 6; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo; echo "=== distill v4 champion (pour bench-eval) ==="
./build-prod/jass --dump-eval-features "$CLEAN" "$ART/feat" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$CLEAN" --scan-eval --eval-features-file "$ART/feat" \
  --target score --score-clip 5000 --score-drop 4900 --l2 1e-4 --max-iter 200 --scale 1000 \
  --material-anchor 1.0 --man-pu 1.0 --king-pu 3.0 --out "$ART/v4.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/v4.pjtw" ] || { echo "ABORT train"; exit 7; }

echo; echo "=== (1) DÉBIT ÉVAL brut (evals/s) ==="
./build-prod/jass --bench-eval "$ART/v4.pjtw" 3000000 2>&1 | tee "$ART/be-scan.log" | grep -iE "evals/s|ns_per"
./build-prod/jass --bench-eval "$V15"          3000000 2>&1 | tee "$ART/be-v15.log"  | grep -iE "evals/s|ns_per"

echo; echo "=== (2) NPS de RECHERCHE (depth-at-movetime 1000ms) ==="
./build-prod/jass --depth-at-movetime "$ART/v4.pjtw" "$V15" 1000 64 2>&1 | tee "$ART/dam-scan.log" | grep -iE "knps|depth avg"
./build-prod/jass --depth-at-movetime hc            "$V15" 1000 64 2>&1 | tee "$ART/dam-hc.log"   | grep -iE "knps|depth avg"

echo; echo "=== (3) NPS de SCAN (cible, best-effort) ==="
SCAN_DIR=/root/jass-scan; SCAN_BIN="$SCAN_DIR/scan_linux"
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src
  [ -d "$SRC" ] || git clone --depth 1 https://github.com/rhalbersma/scan "$SRC" 2>/dev/null || true
  mkdir -p "$SCAN_DIR"; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp "$SRC/scan.ini" "$SCAN_DIR/" 2>/dev/null || true; cp -r "$SRC/data" "$SCAN_DIR/data" 2>/dev/null || true
fi
if [ -x "$SCAN_BIN" ]; then
  ( cd "$SCAN_DIR" && printf 'hub\ninit\npos pos=Wbbbbbbbbbbbbbbbbbbbbeeeeeeeeeewwwwwwwwwwwwwwwwwwww\nlevel move-time=3.0\ngo think\n' \
      | timeout 12 ./scan_linux 2>&1 ) | tee "$ART/scan-nps.log" | grep -oiE "nodes=[0-9]+|nps=[0-9.]+" | tail -4 || echo "  (scan probe non concluant)"
else echo "  (scan indisponible)"; fi

rate(){ grep -oiE 'evals/s=[0-9.eE+]+' "$1" | grep -oE '[0-9.eE+]+$' | head -1; }
knps(){ grep -oiE 'knps~[0-9.]+' "$1" | grep -oE '[0-9.]+' | head -1; }
echo; echo "=========================================================="
echo "        0189 PROFIL DU ×6 NPS — VERDICT"
echo "  débit éval brut : scan-eval=$(rate "$ART/be-scan.log") evals/s   v15=$(rate "$ART/be-v15.log") evals/s"
echo "  NPS recherche   : scan-eval=$(knps "$ART/dam-scan.log") knps   hc=$(knps "$ART/dam-hc.log") knps   (v15≈1325)"
echo "  Scan NPS (cible): $(grep -oiE 'nps=[0-9.]+' "$ART/scan-nps.log" 2>/dev/null | tail -1)"
echo "  → scan-eval evals/s >> v15 mais NPS scan-eval ≈ hc << Scan = goulot MOVEGEN/coeur."
echo "  → scan-eval evals/s ≈/< v15 OU NPS scan-eval << hc = goulot ÉVAL (extras non-incrémentaux ?)."
echo "=========================================================="
