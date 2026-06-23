#!/usr/bin/env bash
# id: ccx33-0436-scan-pruning-ab
# description: TEST DECISIF (cf DIAGNOSTIC_VS_SCAN.md) — on perd vs Scan par COMBINAISONS en milieu de partie et la
# profondeur ne rattrape pas => hypothese : notre ELAGAGE forward (multicut+razor, +50 Elo en self-play) coupe les
# defenses tactiques face a Scan. A/B a depth 11, no-DB des 2 cotes, meme champion 3e-5 :
#   A = elagage ON (defaut bake)   B = elagage OFF (multicut_min_depth=0,razor_max_depth=0)
# Si B >> A (ex. 0.05 -> 0.3) => faiblesse de RECHERCHE recuperable (PAS NNUE). Si B~A => c'est l'EVAL.
# Dump des parties pour analyse combinaisons. 18 parties/cote (deterministe). Ordre de grandeur.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0436-scan-pruning-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-prune-ab; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
D=11; PAIRS=1

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; exit 4; }
say "=== build jass (32-pat, extras champion, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

run(){ # $1=tag $2=search-params(ou vide)
  local tag="$1" sp="$2" extra=""
  [ -n "$sp" ] && extra="--jass-search-params $sp"
  echo "  [match $tag] depth $D, $([ -n "$sp" ] && echo "$sp" || echo 'elagage DEFAUT')"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --scan-bb-size 0 --depth "$D" --pairs "$PAIRS" --dump-games-dir "$ART/games-$tag" $extra >"$W/$tag.log" 2>&1 || { say "  (match $tag echoue)"; tail -4 "$W/$tag.log"|sed 's/^/    /'|tee -a "$RES"; return; }
  local sc; sc=$(grep -oiE "score rate:?\s*[0-9.]+" "$W/$tag.log" | tail -1)
  local wdl; wdl=$(grep -oiE "Jass=[0-9]+\s+Scan=[0-9]+\s+Draws=[0-9]+" "$W/$tag.log" | tail -1)
  say "  $tag : $sc   [$wdl]"; }

say "=== A/B ELAGAGE (champion 3e-5, depth ${D}, no-DB des 2 cotes) ==="
run "A-elagage-ON"  ""
run "B-elagage-OFF" "multicut_min_depth=0,razor_max_depth=0"
say ""
say "================= LECTURE ================="
say "  B >> A (ex 0.05 -> 0.3+) => l'ELAGAGE nous rendait tactiquement aveugles vs Scan => faiblesse de RECHERCHE,"
say "                              recuperable SANS NNUE (re-tuner/desactiver multicut+razor vs adversaires forts)."
say "  B ~ A (~0.05)            => l'elagage n'est PAS le coupable => c'est l'EVAL (shot-vulnerable) => richesse / NNUE."
say "  (parties dumpees dans games-A / games-B pour analyse combinaisons)"
say "==========================================="
