#!/usr/bin/env bash
# id: ccx33-0275-endgame-features
# description: DIRECTION B (représentation). Le verrou finale n'est ni le bruit ni les labels
# (0267/0272) → reste couverture (0274, sur CPX62) ou REPRÉSENTATION. On TESTE les features :
# build avec -DJASS_ENDGAME_FEATURES (NUM_EXTRAS 106→110 : centralité-roi + proximité-roi→ennemi,
# l'interaction-roi que le PST par-case rate). Distillation king-aware sur Scan-d10 (même setup
# que 0272 mais AVEC les features) + autopsie finale. Si endgame-rois < 5.13 (0272 sans features)
# → les features de finale aident → on les intègre (gated→défaut). Sinon → ni couverture ni
# features ni labels = limite plus profonde (bitbases / non-linéarité, à rediscuter).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0275-endgame-features/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MASTER=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw
[ -f "$MASTER" ] || { echo "ABORT: master introuvable"; exit 3; }

echo "=== build king-aware + ENDGAME FEATURES (NUM_EXTRAS=110) ==="
rm -rf build-prod
cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON -DJASS_ENDGAME_FEATURES=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED" "$ART/cmake.log" || { echo "ABORT: features pas activées"; exit 5; }
grep -q "KING-AWARE patterns ENABLED" "$ART/cmake.log" || { echo "ABORT: pas king-aware"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

echo "=== dump features (doit être 110/pos) + distillation SCORE king-aware ==="
$JASS --dump-eval-features "$MASTER" "$ART/featM" 2>&1 | tail -1
python3 pattern_jass/tools/train.py --data "$MASTER" --scan-eval --king-patterns \
    --eval-features-file "$ART/featM" --target score --score-clip 2000 --score-drop 4900 \
    --l2 1e-4 --max-iter 300 --scale 1000 --prune --full-fold --out "$ART/distill-egf.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/distill-egf.pjtw" ] || { echo "ABORT distill"; tail -8 "$ART/train.log"; exit 7; }
grep -q "adapting to the dump width" "$ART/train.log" && echo "trainer a bien adapté à 110 features"

# Elo vs hc
ELO=$($JASS --benchmark-scan-eval "$ART/distill-egf.pjtw" hc 9 60 "$NCPU" 0 2>/dev/null | { W=0;D=0;L=0; while read -r l; do case "$l" in *SCAN_EVAL=*) W=$(echo "$l"|grep -oE 'SCAN_EVAL=[0-9]+'|cut -d= -f2); L=$(echo "$l"|grep -oE 'NNUE=[0-9]+'|cut -d= -f2); D=$(echo "$l"|grep -oE 'Draws=[0-9]+'|cut -d= -f2);; esac; done; echo "${W}-${D}-${L}"; })
ELOV=$(python3 tools/sprt_elo.py --wdl $(echo "$ELO"|tr '-' ' ') 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2)

# autopsie vs Scan
SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1 || { echo "ABORT clone"; exit 4; }; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
SCAN5=""
if [ -x "$SCAN_BIN" ]; then
  GAMES="$ART/games"; mkdir -p "$GAMES"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/distill-egf.pjtw" --scan-bb-size 0 --movetime 0.5 --pairs 2 --dump-games-dir "$GAMES" >"$ART/scan-mt05.log" 2>&1
  SCAN5=$(grep -E 'score rate|ELO estimate' "$ART/scan-mt05.log" | tr '\n' ' ')
  python3 tools/game_autopsy.py --games-dir "$GAMES" --jass /bin/true --scan "$SCAN_BIN" --scan-depth 11 --scan-bb-size 0 --worst 10 --out "$ART/autopsy.txt" 2>"$ART/autopsy.err" || echo "(autopsie skip)"
fi

echo; echo "=========================================================="
echo "   ccx33-0275 — DIRECTION B : FEATURES DE FINALE (centralité + proximité roi)"
echo "----------------------------------------------------------"
echo "  distill+features : Elo_vs_hc(60p)=$ELO elo=$ELOV"
[ -n "$SCAN5" ] && echo "  vs Scan mt0.5 : $SCAN5"
echo "  AUTOPSIE (endgame-rois ; comparer 0272 SANS features = 5.13) :"
sed -n '/PHASE × ROIS/,/par TACTIQUE/p' "$ART/autopsy.txt" 2>/dev/null | head -12
echo "----------------------------------------------------------"
echo "  endgame-rois < 5.13 → les features de finale AIDENT → les intégrer (gated→défaut) + tester sur self-play."
echo "  endgame-rois ~5.13 → features n'aident pas ; combiné à 0274 (couverture) ça tranchera la nature du verrou."
echo "=========================================================="
