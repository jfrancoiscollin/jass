#!/usr/bin/env bash
# id: ccx33-0490-forcing-ext-movetime-v2
# description: LE DECIDEUR "BAKE OR NOT" de ext_forcing (suite 0483/0485). Fixed-depth (d11/d13/d15) a montre que
# ext_forcing est un VRAI levier (0440 : base 0.30/0.38/0.50 -> ext 0.60/0.65/0.73). MAIS a profondeur fixe l'extension
# cherche plus profond GRATUITEMENT sur les lignes forcantes ; sa vraie question est a TEMPS FIXE : le cout en noeuds
# (moins de profondeur ailleurs) mange-t-il le gain tactique ? Test propre, SANS Scan, SANS confond vitesse : jass(eval
# egdbmix) ext_forcing=1 vs jass(eval egdbmix) baseline, MEME binaire, MEME eval, a MOVETIME EGAL (1.0s/coup) sur des
# ouvertures diverses. Le score net capte gain tactique - cout noeuds.
#   ON >> 0.50 (hors IC) => ext_forcing ameliore le jeu reel a temps fixe => LE BAKER au deploiement (defaut ON au jeu).
#   ON ~ 0.50 => le cout en noeuds annule le gain a temps fixe => garder OFF (le gain fixed-depth est un artefact de mesure).
# Shardé sur les coeurs. AUCUN re-entrainement, AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0490-forcing-ext-movetime-v2/artefacts"; mkdir -p "$ART"
W=/root/cw-extmt2; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
MOVETIME=1.0; PAIRS=12; MAXPLIES=180

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

# A = ext_forcing ON, B = baseline. Sharded. RE-RUN de 0487 (perdu au non-flush) : chaque shard ecrit son tally
# RESULT en INCREMENTAL via --progress-file sous $ART => survit au non-flush (committe a chaque heartbeat).
say "=== [RE-RUN propre] ext_forcing ON vs OFF @ movetime ${MOVETIME}s (eval egdbmix, pairs=${PAIRS}, progress-file incremental) ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/egdbmix.pjtw" \
      --jass-b "$J" --pattern-b "$W/egdbmix.pjtw" --movetime "$MOVETIME" --pairs "$PAIRS" \
      --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet \
      --search-params-a "ext_forcing=1" --search-params-b "" \
      --progress-file "$ART/shard-$s.txt" >"$W/sh-$s.log" 2>&1 & done
wait
python3 - "$ART"/shard-*.txt <<'PY' | tee -a "$RES"
import sys,math
A=D=B=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"):
                _,a,d,b=l.split(); A+=int(a); D+=int(d); B+=int(b)
    except: pass
g=A+D+B
if not g: print("  NO GAMES"); sys.exit(0)
rate=(A+0.5*D)/g                    # ext_forcing(ON) score rate
se=math.sqrt(max(rate*(1-rate),1e-9)/g)
lo,hi=rate-1.96*se, rate+1.96*se
print(f"  ext_forcing(ON) vs baseline(OFF) @ movetime : score={rate:.3f}  IC95=[{lo:.3f},{hi:.3f}]  (games={g} ; ON={A} D={D} OFF={B})")
print(f"  LECTURE : IC entierement > 0.50 => BAKER (defaut ON au jeu) ; IC contient 0.50 => le cout noeuds annule le gain => garder OFF.")
PY
say "=== rappel fixed-depth (0483/0485) : 0440 base 0.30/0.38/0.50 (d11/13/15) -> ext 0.60/0.65/0.73 ==="
