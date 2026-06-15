#!/usr/bin/env bash
# id: cpx62-0272-distill-endgame-autopsy
# description: DIAGNOSTIC (cheap, ~40min) — un teacher EXTERNE CORRECT répare-t-il la finale ?
# Le diagnostic consolidé (0265/0266/0267) : notre self-play joue les finales trop faiblement →
# éval systématiquement fausse en finale (0267 : erreurs STABLES, pas du bruit), depth-8 aide
# globalement (+28) mais pas la finale (autopsie 3.22). Donc la finale a besoin de labels
# EXTERNES corrects. On TESTE : distiller king-aware sur le master Scan-d10 (labels Scan
# CORRECTS) puis AUTOPSIER sa finale vs Scan. Si endgame-rois << 3.2 → le teacher correct
# RÉPARE la finale → la voie = blend self-play(force globale) + distill-finale (anchor). Si
# toujours ~3.2 → même les labels Scan ne suffisent pas → limite représentationnelle / features.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0272-distill-endgame-autopsy/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- distille king-aware sur Scan-d10 (score, labels corrects) ---
echo "=== distillation king-aware SCORE sur Scan-d10 ==="
$JASS --dump-eval-features "$MASTER" "$ART/featM" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$MASTER" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --target score --score-clip 2000 --score-drop 4900 \
    --l2 1e-4 --max-iter 300 --scale 1000 --prune --full-fold --out "$ART/distill.pjtw" >"$ART/distill-train.log" 2>&1
[ -f "$ART/distill.pjtw" ] || { echo "ABORT distill"; tail -8 "$ART/distill-train.log"; exit 7; }

# --- ensure Scan ---
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || { echo "ABORT clone Scan"; exit 4; }; chmod +x "$SCAN_BIN" 2>/dev/null || true; fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable"; exit 4; }

# --- match vs Scan (dump) + autopsie phase×rois ---
GAMES="$ART/games"; mkdir -p "$GAMES"
echo "=== match distill vs Scan mt0.5 (dump) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/distill.pjtw" \
    --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
NG=$(ls "$GAMES"/game-*.json 2>/dev/null | wc -l); [ "$NG" -gt 0 ] || { echo "ABORT: pas de parties"; tail -15 "$ART/scan-mt05.log"; exit 8; }
echo "=== autopsie phase×rois (oracle Scan depth 11) ==="
python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" \
    --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err"

echo; echo "=========================================================="
echo "   cpx62-0272 — TEACHER CORRECT (Scan-d10 distill) RÉPARE-T-IL LA FINALE ?"
echo "----------------------------------------------------------"
echo "  distill king-aware vs Scan mt0.5 : ${SCAN5:-?}"
echo "  AUTOPSIE (comparer 0250=3.6 / 0266=3.22 en endgame-rois) :"
sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12
echo "----------------------------------------------------------"
echo "  endgame-rois << 3.2 → le teacher CORRECT répare la finale → voie = BLEND self-play +"
echo "     distill-finale (anchor sélectif par banc EG). Production : self-play global + Scan-finale."
echo "  endgame-rois ~3.2 → même les labels Scan ne suffisent pas → limite représentationnelle"
echo "     (features de finale manquantes) ou besoin de bitbases (teacher PARFAIT, ≤N pièces)."
echo "=========================================================="
