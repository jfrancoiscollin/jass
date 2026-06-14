#!/usr/bin/env bash
# id: cpx62-0250-reautopsy-king
# description: RE-AUTOPSIE king-aware « après » avec bucket PHASE × ROIS — isole la VRAIE part
# rois du ×14 (confondu avec « finale dure »). Re-joue game_autopsy.py (oracle Scan depth 11)
# sur les parties DÉJÀ dumpées par 0248 (local), avec le nouveau croisement phase×roi : dans
# une même phase, perte king vs no-king. Si le ratio reste grand = effet roi réel.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0250-reautopsy-king/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc)
GAMES=/root/jass/jobs/results/cpx62-0248-autopsy-king-vs-scan/artefacts.src/games
NG=$(ls "$GAMES"/game-*.json 2>/dev/null | wc -l)
[ "$NG" -gt 0 ] || { echo "ABORT: parties de 0248 introuvables à $GAMES (box recyclée ?)"; exit 3; }
echo "parties king-aware (0248) trouvées : $NG"

SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  echo "=== Scan absent → install ==="; rm -rf /root/jass-scan
  git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 \
    || { echo "ABORT: clone Scan échoué"; tail -5 "$ART/scan-clone.log"; exit 4; }
  chmod +x "$SCAN_BIN" 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan introuvable"; exit 4; }
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo "=== game_autopsy (oracle depth 11) — bucket PHASE × ROIS ==="
python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" \
    --scan-depth 11 --scan-bb-size 0 --worst 15 --out "$ART/reautopsy-king.txt" 2>"$ART/err.log"
echo; echo "=========================================================="
echo "   ccx33-0249 — RE-AUTOPSIE KING-AWARE : phase × rois (isole l'effet roi)"
sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/reautopsy-king.txt" 2>/dev/null | head -14
echo "=========================================================="
