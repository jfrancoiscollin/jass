#!/usr/bin/env bash
# id: ccx33-0521-combo-ebf-vs-scan
# description: PAYOFF EBF — la recette Scan (single_reply + asym_2_4) baisse-t-elle notre EBF/handicap vs Scan ? Re-mesure
# comme #0/0495 : temps->profondeur d9/12/15, baseline vs COMBO, ratio jass/scan (R(15) baseline ~2,40). Node-EBF via
# nps_vs_scan --jass-search-params (PR #320). Si R(15) COMBO < baseline nettement => le croisement d15 recule => moins de
# handicap movetime vs Scan (le vrai but). AUCUN NNUE. Single-thread (fiable), Scan requis.
# expected_duration: ~30 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-90}"; source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0521-combo-ebf-vs-scan/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; W=/root/cw-cebf; mkdir -p "$W"
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux; CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
preflight_build 1; preflight_note "combo EBF vs Scan d9/12/15 x2 configs" 60; preflight_check
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { echo "ABORT egdb off"; exit 6; }
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { echo "BUILD FAIL"; tail -10 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { echo "ABORT champ"; exit 4; }
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT Scan"; exit 5; }
COMBO="ext_single_reply=1,lmr_first_full_nonpv=2,lmr_first_full_pv=4"
for cfg in baseline combo; do
  SP=""; [ "$cfg" = combo ] && SP="$COMBO"
  echo "--- config=$cfg ($SP) ---" | tee -a "$ART/VERDICT.txt"
  python3 tools/nps_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --jass-search-params "$SP" --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee -a "$ART/VERDICT.txt"
done
echo "=== R(15) combo < baseline (2,40) => handicap movetime vs Scan reduit => la recette Scan aide. ===" | tee -a "$ART/VERDICT.txt"
