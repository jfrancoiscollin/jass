#!/usr/bin/env bash
# id: ccx33-0332-nps-vs-scan
# description: Mesure PROPRE du handicap de vitesse jass vs Scan à PROFONDEUR ÉGALE (le proxy temps de 0330
# était trop bruité). Pour un échantillon de positions, on chronomètre jass→depth D et Scan→depth D. Le ratio
# jass/scan = combien de fois jass est plus lent = EXACTEMENT le facteur de compensation movetime pour le
# benchmark fair permanent (donner ce ×temps à jass = équitable). Dimensionne le levier RECHERCHE.
# expected_duration: ~1-2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-180}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0332-nps-vs-scan/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw  # committé
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$POS" ] || { echo "ABORT: corpus 0328 absent ($POS)"; exit 4; }

preflight_build 1
preflight_note "NPS timing 40 pos × depths 9/12/15 (×2 moteurs)" 90
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée ==="
B=build-full; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
      >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; tail -8 "$ART/cmake.log"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -12 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"

echo "=== mesure NPS (jass vs Scan, depths 9/12/15, 40 positions) ==="
python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" \
    --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee "$ART/nps.log"

echo; echo "=========================================================="
echo "   ccx33-0332 — handicap de vitesse jass vs Scan (à depth égale)"
echo "----------------------------------------------------------"
grep -E '^[[:space:]]*(depth|[0-9]+)[[:space:]]' "$ART/nps.log" || true
echo "   ratio jass/scan = ×temps à donner à jass pour un benchmark fair."
echo "=========================================================="
