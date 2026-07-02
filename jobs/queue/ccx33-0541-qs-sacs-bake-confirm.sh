#!/usr/bin/env bash
# id: ccx33-0541-qs-sacs-bake-confirm
# description: CONFIRMATION RAPIDE (tendance) du bake qs_sacs en JEU MOVETIME. Head-to-head jass(defaut=qs_sacs ON,
# baké main) vs jass(qs_sacs=0), MEME binaire + MEME eval champion egdbmix, dilf combos, movetime, peu de parties
# (n=610). Le make-or-break de la detection par-position (+0.04 @0.3s) se convertit-il en PARTIES completes ? Si
# A(ON) score-rate > 0.53 hors bruit => le bake se paie en jeu reel, on enchaine sweep+self-play. AUCUN NNUE.
# expected_duration: ~30-45 min.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0541-qs-sacs-bake-confirm/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-bakeconfirm; rm -rf "$W"; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.3; PAIRS=1; MAXPLIES=180
PROG="$ART/progress"

say "=== build jass depuis main (qs_sacs BAKED ON par defaut) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$EGDBMIX" | gunzip > "$W/champ.pjtw" || { say "ABORT champ egdbmix absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  sanity dump-sacs (defaut ON) : $(head -1 "$DILF" | sed 's/#.*//' | "$J" --dump-sacs 2>/dev/null | head -1)"

say ""
say "=== head-to-head  A=defaut(qs_sacs ON)  vs  B=qs_sacs=0   @ movetime ${MT}s, dilf n=305 x${PAIRS}pair ==="
for s in $(seq 0 $((NCPU-1))); do
  ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/champ.pjtw" \
       --jass-b "$J" --pattern-b "$W/champ.pjtw" --movetime "$MT" --pairs "$PAIRS" \
       --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
       --search-params-a "" --search-params-b "qs_sacs=0" \
       --progress-file "${PROG}.$s" >"$W/out.$s" 2>"$W/err.$s"; echo "DONE $s" ) &
done
wait

say ""
say "=== agrege (A=qs_sacs ON, B=qs_sacs OFF) ==="
python3 - "$PROG" "$NCPU" <<'PY' 2>&1 | tee -a "$RES"
import sys, math
prog, nc = sys.argv[1], int(sys.argv[2])
A=B=D=0
for s in range(nc):
    try:
        last=[l for l in open(f"{prog}.{s}") if l.startswith("RESULT")][-1]
        _,a,d,b=last.split(); A+=int(a); D+=int(d); B+=int(b)
    except Exception as e:
        print(f"  (shard {s} sans resultat: {e})")
g=A+B+D; rate=(A+0.5*D)/g if g else 0.0
elo=(-400*math.log10(1.0/rate-1.0)) if 0.0<rate<1.0 else 0.0
# IC ~ +-1/sqrt(N) en rate
se=(0.5/ (g**0.5)) if g else 1.0
print(f"  games={g}  A(ON)={A}  B(OFF)={B}  D={D}")
print(f"  A(ON) score-rate = {rate:.3f} +-{1.96*se:.3f}   elo(ON-OFF) ~ {elo:+.0f}")
verd = "BAKE CONFIRME en jeu (ON>OFF hors bruit)" if rate-1.96*se>0.50 else ("tendance + mais dans le bruit" if rate>0.50 else "parite/regression — a investiguer")
print(f"  => {verd}")
PY
say "=== fin confirm bake qs_sacs ==="
