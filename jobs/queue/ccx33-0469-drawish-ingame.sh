#!/usr/bin/env bash
# id: ccx33-0469-drawish-ingame
# description: DERNIER item C2 cheap : JASS_DRAWISH_SCALING teste EN JEU sur le champion COURANT (egdbmix). drawish = la
# seule non-linearite localisee de Scan (search.cpp:249, param runtime drawish_scaling, TOUJOURS compile) : en finale
# drawish (gagnant <=3 pieces vs roi adverse => /8 ; rois egaux & |delta-men|<=1 => /2) elle retrecit le score vers la nulle
# pour eviter de jeter des demi-points dans des finales ingagnables. RAPPEL : 0353 l'a deja jugee NEUTRE en jeu (vieux
# champion) ; ici on CONFIRME sur egdbmix avec IC, pour clore C2 proprement. Deux mesures : (A) self-play A/B drawish ON vs
# OFF (meme champion, juge sensible, depth fixe) ; (B) vs Scan eval-pur depth-FIXE (drawish ON vs Scan et OFF vs Scan, no-DB
# -- methodo : depth-fixe, JAMAIS movetime egal). Si ON ~ OFF (IC contient 0.50 / pas d'ecart vs Scan) => NEUTRE confirme,
# item C2 clos. Si ON >> OFF => le levier vit (rare vu 0353). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0469-drawish-ingame/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-drawish; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SP_PAIRS=8; SCAN_PAIRS=14; DSP=9; DSCAN=11
DRAW="drawish_scaling=1"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — test B saute)"
say "=== build jass standard (drawish param TOUJOURS compile, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
unset JASS_EGDB_PATH

say ""; say "=== (A) SELF-PLAY A/B : drawish ON (side A) vs OFF (side B), meme champion egdbmix, depth ${DSP} ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/champ.pjtw" --jass-b "$J" --pattern-b "$W/champ.pjtw" \
    --search-params-a "$DRAW" --depth "$DSP" --pairs "$SP_PAIRS" --max-plies 200 --shard "$s" --nshards "$NCPU" --quiet >"$W/sp.$s" 2>&1 &
done; wait
python3 - "$W"/sp.* <<'PY' | tee -a "$RES"
import sys,math
a=d=b=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
    except: pass
g=a+d+b
if not g: print("  (self-play : aucun resultat)"); sys.exit(0)
sc=(a+0.5*d)/g
se=math.sqrt(max(sc*(1-sc),1e-9)/g)
print(f"  self-play drawish ON vs OFF : {sc:.3f}  (W={a} D={d} L={b}, N={g})  IC95~[{sc-1.96*se:.3f},{sc+1.96*se:.3f}]")
print(f"  => 0.50 DANS l'IC => NEUTRE (drawish ne change pas la force en self-play) ; >0.55 => ON aide.")
PY

if [ "$HAVE_SCAN" = 1 ]; then
say ""; say "=== (B) vs SCAN eval-pur depth-FIXE d${DSCAN}, no-DB : drawish ON vs Scan, puis OFF vs Scan ==="
rate_of(){ grep -oiE "score rate:\s*[0-9.]+" "$1" | grep -oE "[0-9.]+" | tail -1; }
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" --scan-bb-size 0 \
    --depth "$DSCAN" --pairs "$SCAN_PAIRS" --jass-search-params "$DRAW" >"$W/scan-on.log" 2>&1 || say "  (vs-Scan ON echoue)"
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" --scan-bb-size 0 \
    --depth "$DSCAN" --pairs "$SCAN_PAIRS" >"$W/scan-off.log" 2>&1 || say "  (vs-Scan OFF echoue)"
RON=$(rate_of "$W/scan-on.log"); ROFF=$(rate_of "$W/scan-off.log")
say "  vs Scan (eval-pur d${DSCAN}) : drawish ON=${RON:-NA}   OFF=${ROFF:-NA}   (rappel 0353 : neutre)"
fi

say ""; say "================= LECTURE ================="
say "  ON ~ OFF (self-play IC contient 0.50 ET pas d'ecart vs Scan) => DRAWISH NEUTRE confirme sur egdbmix"
say "       => dernier item C2-(3) CLOS (neutre, comme 0353). Reste 0465 (donnees-mu) avant evaluation C3/C4 du gate."
say "  ON >> OFF => drawish aide => le levier vit, le baker en defaut (drawish_scaling=1)."
say "=========================================="
