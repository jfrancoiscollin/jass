#!/usr/bin/env bash
# id: cpx62-0353-drawish-confirm
# description: CONFIRME la magnitude du drawish (0351: vs Scan OFF=0.028→ON=0.139, mais 108p = bruité, OFF bas
# suspect). Ici BEAUCOUP de parties (depth-fixe = rapide) vs Scan à profondeur égale d9 ET d11, drawish ON vs OFF.
# ON > OFF net et reproductible → baker drawish_scaling=1 (jeu + self-play). Sinon → c'était du bruit.
# expected_duration: ~1.5 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-150}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0353-drawish-confirm/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1; preflight_train 240000 1; preflight_note "4 matchs depth-fixe ×270 parties vs Scan" 100; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

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

rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
vs(){ # <tag> <jd> <extra-params>
  local tag="$1" jd="$2" sp="$3"; local lg="$ART/$tag.log"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    ${sp:+--jass-search-params "$sp"} --scan-bb-size 0 --jass-depth "$jd" --scan-depth 9 --pairs 15 --max-plies 160 >"$lg" 2>&1 || true
  echo "  $tag : $(rate "$lg")"; }
echo "=== vs Scan, 270 parties/condition ==="
vs d9_off  9 ""
vs d9_on   9 "drawish_scaling=1"
vs d11_off 11 ""
vs d11_on  11 "drawish_scaling=1"

echo; echo "=========================================================="
echo "   cpx62-0353 — CONFIRMATION drawish vs Scan (270 parties/condition)"
echo "----------------------------------------------------------"
echo "   jass d9  vs Scan d9 :  OFF=$(rate "$ART/d9_off.log")   ON=$(rate "$ART/d9_on.log")"
echo "   jass d11 vs Scan d9 :  OFF=$(rate "$ART/d11_off.log")  ON=$(rate "$ART/d11_on.log")"
echo "----------------------------------------------------------"
echo "   ON > OFF net aux deux profondeurs → baker drawish_scaling=1 (jeu + self-play). Sinon → bruit."
echo "=========================================================="
