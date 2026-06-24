#!/usr/bin/env bash
# id: ccx33-0451-forcing-movetime
# description: DECIDEUR du fix no_reduce_forcing. 0447 : +10pts conversion combinaisons (0.246->0.348) MAIS -1.6 plies a
# temps fixe (le check coute un movegen). Le test a profondeur fixe (self-play 0.500) ne capture PAS ce cout. Ici on
# mesure le NET en conditions reelles : jass(baseline) vs Scan ET jass(fix) vs Scan a MOVETIME EGAL (300ms des 2 cotes,
# no-DB), sur (A) le pool standard = jeu general (le -1.6 plies nuit-il ?) et (B) un echantillon de combinaisons = tactique
# (le gain survit-il au temps ?). Si fix >= baseline en general ET > baseline en combos => le gain bat le cout => DEFAUT.
# Sinon => optimiser le check (has_capture rapide / pre-filtre) avant de trancher. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0451-forcing-movetime/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-forcing-mt; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
FENS=data/dilf_combinations.fen
FIX="no_reduce_forcing=1"; MT=0.3; GEN_PAIRS=14; COMBO_N=80

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
say "=== build jass (fix dispo, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH
grep -vE '^\s*(#|$)' "$FENS" | head -n "$COMBO_N" > "$W/combo_sample.fen"

rate_of(){ grep -oiE "score rate:\s*[0-9.]+" "$1" | grep -oE "[0-9.]+" | tail -1; }
conv(){ python3 - "$1" "$FENS" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]
stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0].strip()
w=ndum=0; jw_w=jw_n=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    jatt=(jiw and s=="W") or ((not jiw) and s=="B")
    aw=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0)
    if jatt: jw_w+=aw; jw_n+=1
print(f"{jw_w/jw_n:.3f}" if jw_n else "NA")
PY
}
runmatch(){ # $1=tag $2=openings-file(or "std") $3=search-params $4=dumpdir(or "")
  local tag="$1" opf="$2" sp="$3" dd="$4" extra=""
  [ "$opf" != "std" ] && extra="--openings-file $opf"
  [ -n "$sp" ] && extra="$extra --jass-search-params $sp"
  [ -n "$dd" ] && extra="$extra --dump-games-dir $dd"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --scan-bb-size 0 --jass-movetime "$MT" --scan-movetime "$MT" --pairs "${5:-2}" $extra >"$W/$tag.log" 2>&1 || say "  (match $tag echoue)"
}

say ""; say "=== (A) JEU GENERAL vs Scan @${MT}s (pool standard, ${GEN_PAIRS} pairs) ==="
runmatch gen-base std ""    "" "$GEN_PAIRS"
runmatch gen-fix  std "$FIX" "" "$GEN_PAIRS"
GB=$(rate_of "$W/gen-base.log"); GF=$(rate_of "$W/gen-fix.log")
say "  jass vs Scan (general) : baseline=${GB}   fix=${GF}"

say ""; say "=== (B) COMBINAISONS vs Scan @${MT}s (${COMBO_N} positions) ==="
runmatch combo-base "$W/combo_sample.fen" ""    "$ART/games-combo-base" 1
runmatch combo-fix  "$W/combo_sample.fen" "$FIX" "$ART/games-combo-fix"  1
CB=$(conv "$ART/games-combo-base"); CF=$(conv "$ART/games-combo-fix")
say "  conversion combinaisons : baseline=${CB}   fix=${CF}   (d11 fixe rappel 0447 : 0.246->0.348)"

say ""; say "================= VERDICT ================="
say "  general fix>=base ET combos fix>base  => le gain tactique bat le cout vitesse => PASSER no_reduce_forcing EN DEFAUT."
say "  general fix<base                       => -1.6 plies nuit au jeu general => optimiser le check (has_capture rapide)"
say "                                            ou gater plus etroitement avant de trancher."
say "=========================================="
