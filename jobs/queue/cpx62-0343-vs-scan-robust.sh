#!/usr/bin/env bash
# id: cpx62-0343-vs-scan-robust
# description: SOLIDIFIE le combo vs Scan + tranche l'ajout lmp5+rfp7 — DIRECTEMENT vs Scan, en UN SEUL build
# grâce au flag --jass-search-params (câblé ce jour). ARM A = combo baké (défaut) vs Scan ; ARM B = combo +
# lmp_max_depth=5,rfp7 vs Scan. mt égal 1.0, 54 parties/bras. B>A → l'ajout aide vs Scan → baker.
# expected_duration: ~5 h (2 bras × 72 parties vs Scan)
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-360}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0343-vs-scan-robust/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
ADD="lmp_max_depth=5,rfp_max_depth=7,rfp_margin=70"

preflight_build 1
preflight_train 240000 1
preflight_match 54 1.0 150; preflight_match 54 1.0 150
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée (UN seul build — flag --jass-search-params) ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
echo "=== train éval ==="
"$JASS" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/train.log"; exit 9; }
manifest_write "$ART/eval.pjtw" "DISTILL=Scan SRC=0314 FULL-aligned combo-baked" "$DATA" >/dev/null

rate(){ grep -E 'score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
elo(){ grep -E 'ELO estimate' "$1" | grep -oE '\-?[0-9]+' | head -1; }
echo "=== ARM A : combo baké vs Scan (mt1.0, 54 parties) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    --scan-bb-size 0 --movetime 1.0 --pairs 3 --max-plies 150 --allow-long-movetime >"$ART/vs-combo.log" 2>&1 || true
echo "=== ARM B : combo + ${ADD} vs Scan (même build, --jass-search-params) ==="
python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    --jass-search-params "$ADD" \
    --scan-bb-size 0 --movetime 1.0 --pairs 3 --max-plies 150 --allow-long-movetime >"$ART/vs-add.log" 2>&1 || true

echo; echo "=========================================================="
echo "   cpx62-0341 — combo (+lmp5/rfp7 ?) vs Scan, mt1.0, 54 parties/bras"
echo "----------------------------------------------------------"
echo "   ARM A combo baké        : rate=$(rate "$ART/vs-combo.log")  Elo=$(elo "$ART/vs-combo.log")"
echo "   ARM B combo+lmp5+rfp7   : rate=$(rate "$ART/vs-add.log")  Elo=$(elo "$ART/vs-add.log")"
echo "----------------------------------------------------------"
echo "   Rappel : baseline sans combo = 0.097 ; combo (0338, 36p) = 0.139."
echo "   B > A nettement → baker lmp5+rfp7. A solide > 0.097 → le combo tient."
echo "=========================================================="
