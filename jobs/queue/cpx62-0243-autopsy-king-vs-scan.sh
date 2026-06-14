#!/usr/bin/env bash
# id: cpx62-0243-autopsy-king-vs-scan
# description: AUTOPSIE « APRÈS » (king-aware, sur la box RAPIDE). Fait jouer l'éval
# KING-AWARE du loop 0241 (gen8) contre Scan + dissèque coup par coup (game_autopsy :
# accord + perte d'éval par phase × ROIS × tactique). À comparer à l'autopsie men-only
# 0238 (« avant ») : le fix rois referme-t-il l'effondrement sur les positions à rois ?
# Scan s'AUTO-INSTALLE (git clone rhalbersma/scan) → ce job (et les futurs vs-Scan) peut
# tourner sur CPX62, plus besoin de sérialiser sur CCX33. Matchs BORNÉS au movetime.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0243-autopsy-king-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

# --- ensure Scan (auto-install : le repo livre scan_linux pré-compilé + data/) ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  echo "=== Scan absent → install (git clone rhalbersma/scan) ==="
  rm -rf /root/jass-scan
  git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 \
    || { echo "ABORT: clone Scan échoué (réseau ?)"; tail -5 "$ART/scan-clone.log"; exit 4; }
  chmod +x "$SCAN_BIN" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable après install"; exit 4; }
echo "scan: $SCAN_BIN ($(ls -lh "$SCAN_BIN" | awk '{print $5}'))"

# --- build KING-AWARE jass (pour charger correctement l'éval king-aware de 0241) ---
rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: build pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- éval king-aware du loop 0241 (gen8, repli gen7) ---
EVAL=""
for cand in /root/jass/jobs/results/cpx62-0241-kingloop-scaled/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/cpx62-0241-kingloop-scaled/artefacts.src/gen7.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: éval king-aware de 0241 introuvable"; exit 6; }
echo "EVAL (king-aware) = $EVAL"

# --- 1) match vs Scan avec dump (mt0.5s, pairs=3 → 54 parties) ---
GAMES="$ART/games"; mkdir -p "$GAMES"
echo "=== match king-aware vs Scan (mt0.5s, dump) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$EVAL" \
    --scan-bb-size 0 --movetime 500 --pairs 3 --dump-games-dir "$GAMES" >"$ART/match.log" 2>&1
echo "  $(grep -E 'score rate|ELO estimate' "$ART/match.log" | tr '\n' ' ')"
NG=$(ls "$GAMES"/game-*.json 2>/dev/null | wc -l); echo "  parties sauvées : $NG"
[ "$NG" -gt 0 ] || { echo "ABORT: aucune partie sauvée"; tail -20 "$ART/match.log"; exit 7; }

# --- 2) phase-of-loss + 3) autopsie Scan-oracle ---
python3 tools/analyze_loss_by_pieces.py --games-dir "$GAMES" 2>&1 | tee "$ART/phase.log" | tail -16 || echo "(phase skip)"
echo "=== AUTOPSIE Scan-oracle king-aware (depth 11) ==="
python3 tools/game_autopsy.py --games-dir "$GAMES" --jass "$JASS" --scan "$SCAN_BIN" \
    --scan-depth 11 --scan-bb-size 0 --worst 30 --out "$ART/autopsy-king-report.txt" 2>"$ART/autopsy.err"
echo
echo "=========================================================="
echo "   cpx62-0243 — AUTOPSIE KING-AWARE vs Scan (« après »)"
echo "   à comparer à 0238 (men-only « avant ») : l'accord sur les positions à ROIS remonte-t-il ?"
echo "   rapport : artefacts/autopsy-king-report.txt"
echo "=========================================================="
