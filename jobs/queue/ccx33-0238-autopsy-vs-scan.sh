#!/usr/bin/env bash
# id: ccx33-0238-autopsy-vs-scan
# description: AUTOPSIE — fait jouer notre MEILLEURE éval (full-fold 0227 gen8 / repli 0231)
# contre Scan en SAUVANT les parties (--dump-games-dir), puis les dissèque coup par coup avec
# Scan comme ORACLE (game_autopsy.py) : accord de coup + perte d'éval ventilés par PHASE ×
# ROIS × TACTIQUE + galerie des pires bévues (FENs). But : capter CE QUI NOUS MANQUE
# (hypothèse : effondrement en finale / dès qu'il y a des rois — patterns men-only).
# Matchs BORNÉS au movetime (pas de depth fixe non plafonné, cf. le piège de 0235).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0238-autopsy-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable à $SCAN_BIN — autopsie impossible sans oracle"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy
echo "geometry: $(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)") patterns"

# --- meilleure éval 32-pat full-fold dispo localement ---
EVAL=""
for cand in /root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/gen8.pjtw \
            /root/jass/jobs/results/ccx33-0231-rfe-baseline32/artefacts.src/gen8.pjtw; do
  [ -f "$cand" ] && { EVAL="$cand"; break; }
done
[ -n "$EVAL" ] || { echo "ABORT: aucun gen8 32-pat local (0227/0231)"; exit 6; }
echo "EVAL = $EVAL"

# --- 1) jouer vs Scan en SAUVANT les parties (9 ouvertures × 3 paires × 2 = 54 parties, mt0.5s) ---
GAMES="$ART/games"; mkdir -p "$GAMES"
echo "=== match vs Scan (mt0.5s, dump) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$EVAL" \
    --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/match.log" 2>&1
echo "  $(grep -E 'score rate|ELO estimate' "$ART/match.log" | tr '\n' ' ')"
NG=$(ls "$GAMES"/game-*.json 2>/dev/null | wc -l); echo "  parties sauvées : $NG"
[ "$NG" -gt 0 ] || { echo "ABORT: aucune partie sauvée"; tail -20 "$ART/match.log"; exit 7; }

# --- 2) phase-of-loss (best-effort, ne fait pas échouer le job) ---
echo "=== phase-of-loss (analyze_loss_by_pieces) ==="
python3 tools/analyze_loss_by_pieces.py --games-dir "$GAMES" 2>&1 | tee "$ART/phase.log" | tail -20 \
  || echo "  (analyze_loss_by_pieces sauté)"

# --- 3) AUTOPSIE Scan-oracle coup par coup (le livrable principal) ---
echo "=== AUTOPSIE Scan-oracle (depth 11) ==="
python3 tools/game_autopsy.py --games-dir "$GAMES" --jass "$JASS" --scan "$SCAN_BIN" \
    --scan-depth 11 --scan-bb-size 0 --worst 30 --out "$ART/autopsy-report.txt" 2>"$ART/autopsy.err"
echo
echo "=========================================================="
echo "   ccx33-0238 — AUTOPSIE vs Scan : où/combien on perd"
echo "   (accord de coup + perte d'éval par phase × rois × tactique ; pires bévues)"
echo "   rapport complet : artefacts/autopsy-report.txt"
echo "=========================================================="
