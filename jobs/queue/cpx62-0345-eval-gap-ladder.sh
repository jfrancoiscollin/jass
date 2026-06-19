#!/usr/bin/env bash
# id: cpx62-0345-eval-gap-ladder
# description: PHASE 2 — mesure du GAP D'ÉVAL résiduel vs Scan, à PROFONDEUR ÉGALE (méthodo permanente), avec
# le combo recherche baké. Échelle : jass à d9..d13 contre Scan d9. Le point où jass croise 0.5 = le gap
# d'éval EN PLIES. Beaucoup de parties (depth-fixe = rapide) pour battre le bruit. Dit combien il reste à
# combler côté éval avant de choisir l'attaque (distillation plus profonde ? terme d'éval manquant ?).
# expected_duration: ~2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-200}"
source jobs/lib/preflight.sh
source jobs/lib/manifest.sh
ART="/root/jass/jobs/results/cpx62-0345-eval-gap-ladder/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DATA=/root/jass/jobs/results/cpx62-0327-scan-selfplay-distill/artefacts/old-scan.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
[ -f "$DATA" ] || { echo "ABORT: old-scan.jnnw absent"; exit 4; }

preflight_build 1
preflight_train 240000 1
preflight_note "échelle depth-fixe vs Scan (~600 parties, rapide)" 110
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indisponible"; exit 5; }

echo "=== build jass FULL Scan-alignée (combo baké) ==="
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
[ -f "$ART/eval.pjtw" ] || { echo "TRAIN FAIL"; tail -10 "$ART/train.log"; exit 9; }

rate(){ grep -E 'score rate' "$1" | grep -oE '0\.[0-9]+' | head -1; }
# <name> <jass-depth> <scan-depth> <pairs>
ladder(){ local name="$1" jd="$2" sd="$3" pr="$4"; local lg="$ART/L-$name.log"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$ART/eval.pjtw" \
    --scan-bb-size 0 --jass-depth "$jd" --scan-depth "$sd" --pairs "$pr" --max-plies 160 >"$lg" 2>&1 || true
  echo "  jass d${jd} vs Scan d${sd} ($((pr*18))p): rate=$(rate "$lg")"; }

echo "=== échelle de profondeur (éval combo) vs Scan d9 ==="
ladder eq9   9  9 8
ladder j10  10  9 8
ladder j11  11  9 6
ladder j12  12  9 5
ladder j13  13  9 4

echo; echo "=========================================================="
echo "   cpx62-0345 — GAP D'ÉVAL résiduel (profondeur égale, combo baké) vs Scan d9"
echo "----------------------------------------------------------"
for n in eq9 j10 j11 j12 j13; do printf "  %-5s rate=%s\n" "$n" "$(rate "$ART/L-$n.log")"; done
echo "----------------------------------------------------------"
echo "   Le +N plies où le rate croise 0.5 = le gap d'éval EN PLIES (rappel 0330 : ~2-4)."
echo "=========================================================="
