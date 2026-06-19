#!/usr/bin/env bash
# id: ccx33-0351-drawish-test
# description: ÉTAPE 1 (briques finale) — teste la NON-LINÉARITÉ de Scan qu'on avait codée et jamais essayée
# en jeu : le drawish-material scaling, maintenant appliqué au LEAF pattern (param runtime drawish_scaling).
# 0349 a localisé le gap d'éval en finale (≤7p corr 0.39) → candidat n°1. Juge : (A) self-play SENSIBLE
# drawish=1 vs drawish=0 (même éval, --benchmark-search-params) ; (B) vs Scan profondeur-égale (où la finale
# compte). >0.55 → la brique aide → la baker (ON par défaut).
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-170}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0351-drawish-test/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
MT=700; PAIRS=5; DCAP=30
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "A/B drawish self-play 90p + vs Scan depth-égale" 110
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }

echo "=== build + train éval ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >/dev/null 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 --prune --lowmem --full-fold \
  --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/train.log"; exit 9; }

rate(){ grep -E 'score rate|A score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
echo "=== (A) self-play SENSIBLE : drawish_scaling=1 vs 0 (même éval, ${MT}ms, $((PAIRS*18)) parties) ==="
"$JASS" --benchmark-search-params "$ART/eval.pjtw" "drawish_scaling=1" "" "$DCAP" "$PAIRS" 1 "$MT" >"$ART/ab.log" 2>&1 || true
AB=$(rate "$ART/ab.log")
echo "=== (B) vs Scan profondeur-égale d9 : drawish ON vs baseline ==="
if [ -x "$SCAN_BIN" ]; then
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    --jass-search-params "drawish_scaling=1" --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 >"$ART/vs-on.log" 2>&1 || true
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 >"$ART/vs-off.log" 2>&1 || true
fi

echo; echo "=========================================================="
echo "   ccx33-0351 — DRAWISH-SCALING en jeu (la non-linéarité de Scan oubliée)"
echo "----------------------------------------------------------"
echo "   (A) self-play drawish=1 vs drawish=0 : A-rate=${AB:-NA}   <-- métrique sensible"
echo "   (B) vs Scan d9 : drawish OFF=$(rate "$ART/vs-off.log")   drawish ON=$(rate "$ART/vs-on.log")"
echo "----------------------------------------------------------"
echo "   A-rate > 0.55 net → la brique drawish AIDE → la baker (drawish_scaling=1 par défaut)."
echo "   ≈0.5 → la non-linéarité ne suffit pas → passer aux résidus finale + diff source Scan."
echo "=========================================================="
