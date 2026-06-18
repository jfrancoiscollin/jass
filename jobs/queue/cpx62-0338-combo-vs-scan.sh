#!/usr/bin/env bash
# id: cpx62-0338-combo-vs-scan
# description: VALIDATION du combo recherche baké (multicut+razor) vs Scan. Build COMBO (main baké) + build
# BASELINE (defaults d'avant, via sed vérifié). Mesure (a) le BRANCHEMENT (nps_vs_scan, déterministe : le
# combo aplatit-il l'arbre 2.0→ vers 1.28 ?) et (b) le score vs Scan à TEMPS ÉGAL (le combo achète de la
# profondeur → doit marquer plus). C'est le test qui dit si le levier recherche se traduit en points vs Scan.
# expected_duration: ~3.5-4 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-300}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0338-combo-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }
[ -f "$POS" ]  || { echo "ABORT: corpus 0328 absent"; exit 4; }

preflight_build 2
preflight_train 240000 1
preflight_note "nps×2 builds (40 pos × d9/12/15)" 50
preflight_match 36 1.0 150; preflight_match 36 1.0 150
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
build_it(){ local dir="$1"; rm -rf "$dir"
  cmake -S . -B "$dir" $CMK >"$ART/$dir-cmake.log" 2>&1
  grep -q "EXTERNAL EGDB ENABLED" "$ART/$dir-cmake.log" || { echo "$dir: egdb off"; return 1; }
  cmake --build "$dir" -j"$(mem_safe_jobs)" --target jass >"$ART/$dir-build.log" 2>&1 || { echo "$dir BUILD FAIL"; tail -8 "$ART/$dir-build.log"; return 1; }
}
echo "=== build COMBO (main baké : multicut+razor) ==="
build_it build-combo || exit 6
JC="$PWD/build-combo/jass"

echo "=== revert defaults → build BASELINE ==="
sed -i -E 's/(razor_max_depth[[:space:]]*=[[:space:]]*)4;/\10;/; s/(multicut_min_depth[[:space:]]*=[[:space:]]*)6;/\10;/; s/(multicut_moves[[:space:]]*=[[:space:]]*)8;/\16;/; s/(multicut_cuts[[:space:]]*=[[:space:]]*)2;/\13;/' src/search_params.hpp
grep -qE 'int razor_max_depth = 0;' src/search_params.hpp && grep -qE 'int multicut_min_depth = 0;' src/search_params.hpp || { echo "ABORT: sed revert raté"; git checkout -- src/search_params.hpp; exit 7; }
build_it build-base || { git checkout -- src/search_params.hpp; exit 6; }
JB="$PWD/build-base/jass"
git checkout -- src/search_params.hpp   # restaure le baké

echo "=== train éval (partagée par les 2 builds) ==="
"$JC" --dump-eval-features "$DATA" "$ART/e.feat" >"$ART/dump.log" 2>&1
python3 pattern_jass/tools/train.py --data "$DATA" --scan-eval --eval-features-file "$ART/e.feat" \
  --target score --score-drop 3000 --tempo-stage --l2 1e-4 --max-iter 300 --scale 1000 \
  --prune --lowmem --full-fold --out "$ART/eval.pjtw" >"$ART/train.log" 2>&1
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -8 "$ART/train.log"; exit 9; }

echo "=== (a) BRANCHEMENT : nps_vs_scan (baseline vs combo) ==="
echo "--- BASELINE ---" | tee "$ART/nps.txt"
python3 tools/nps_vs_scan.py --jass "$JB" --scan "$SCAN_BIN" --positions "$POS" --jass-pattern "$ART/eval.pjtw" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee -a "$ART/nps.txt"
echo "--- COMBO ---" | tee -a "$ART/nps.txt"
python3 tools/nps_vs_scan.py --jass "$JC" --scan "$SCAN_BIN" --positions "$POS" --jass-pattern "$ART/eval.pjtw" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee -a "$ART/nps.txt"

echo "=== (b) vs Scan à TEMPS ÉGAL (mt1.0, 36 parties) ==="
rate(){ grep -E 'score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
python3 tools/calibrate_vs_scan.py --jass "$JB" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" --scan-bb-size 0 --movetime 1.0 --pairs 2 --max-plies 150 --allow-long-movetime >"$ART/vs-base.log" 2>&1 || true
python3 tools/calibrate_vs_scan.py --jass "$JC" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" --scan-bb-size 0 --movetime 1.0 --pairs 2 --max-plies 150 --allow-long-movetime >"$ART/vs-combo.log" 2>&1 || true

echo; echo "=========================================================="
echo "   cpx62-0338 — combo recherche baké vs Scan"
echo "----------------------------------------------------------"
echo "  (a) branchement (temps/pos à d9/d12/d15) — voir nps.txt :"
grep -E '^\s*(9|12|15)\s' "$ART/nps.txt" | sed 's/^/      /'
echo "  (b) vs Scan mt1.0 :  baseline=$(rate "$ART/vs-base.log") ; combo=$(rate "$ART/vs-combo.log")"
echo "----------------------------------------------------------"
echo "  combo: temps/pos à d12/d15 PLUS BAS que baseline → arbre aplati (gain confirmé)."
echo "  combo vs Scan > baseline vs Scan → le levier recherche se traduit en points vs Scan."
echo "=========================================================="
