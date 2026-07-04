#!/usr/bin/env bash
# id: cpx62-0561-corner-confirm
# description: CONFIRMATION du COIN (JFC "Confirme le coin"). A 0560 le bras corner (probcut+lmr_asym+multicut) pointait
# a +30 elo mais sur 47 games seulement (IC [0.41,0.67] = non concluant) ; corner+nmp a -28 sur 173. On relance
# UNIQUEMENT ces 2 bras avec assez de games (~600/bras, PAIRS=2) pour resserrer l IC. Baseline = ERE-GEN1
# (qs_threat_ext=0). movetime 0.3s, dilf, eval gen1. NOUVEAU vs 0560 : capture stderr/exit par shard + compte de crashs
# (les 47 games du coin sentent le shard qui plante sur multicut_min_depth=4) ; RESULTS/RANKING committes JOB-SIDE
# (robuste au bug runner qui a rendu RESULTS.txt vide a 0560). Si corner >0.5 hors-IC => premier levier search qui paie
# au jeu. Sinon on referme la phase EBF. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0561-corner-confirm/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0561-corner-confirm/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
RANK="$ART/RANKING.txt"; : > "$RANK"
W=/root/cw-corner; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.3; PAIRS=2; MAXPLIES=180
BASE="qs_threat_ext=0"

commit_to_main(){ local abspath="$1" relpath="$2" msg="$3"
  for a in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob; blob=$(git hash-object -w "$abspath") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$relpath"
    local tree; tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    local commit; commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main)
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    sleep $((a*3))
  done; return 1; }

say "=== build jass depuis main (archi complete) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
say "  baseline = ERE-GEN1 ($BASE) ; movetime ${MT}s ; PAIRS=$PAIRS ; eval gen1 ; HEAD $(git log --oneline -1|cat)"

ARMS=(
  "corner|probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4"
  "corner+nmp|probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4,eg_no_nmp=0"
)
run_arm(){ local name="$1" lev="$2"; local prog="$ART/prog_${name}"
  say ""; say "=== BRAS ${name}  (A=$BASE,$lev  vs  B=$BASE)  @ mt${MT}s dilf x${PAIRS} ==="
  for s in $(seq 0 $((NCPU-1))); do
    ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen1.pjtw" \
        --jass-b "$J" --pattern-b "$W/gen1.pjtw" --movetime "$MT" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$BASE,$lev" --search-params-b "$BASE" \
        --progress-file "${prog}.$s" >"$W/o_${name}.$s" 2>&1; echo "$?" >"$W/rc_${name}.$s" ) &
  done; wait
  # compte de crashs / shards muets
  local crash=0 mute=0
  for s in $(seq 0 $((NCPU-1))); do
    local rc; rc=$(cat "$W/rc_${name}.$s" 2>/dev/null || echo 99)
    [ "$rc" != "0" ] && crash=$((crash+1))
    grep -qiE 'traceback|segfault|core dumped|assert|abort' "$W/o_${name}.$s" 2>/dev/null && crash=$((crash+1))
    [ -s "${prog}.$s" ] || mute=$((mute+1))
  done
  say "  shards: crashs/erreurs=$crash  muets=$mute / $NCPU"
  [ "$crash" -gt 0 ] && { say "  --- extrait 1er shard en erreur ---"; for s in $(seq 0 $((NCPU-1))); do [ "$(cat "$W/rc_${name}.$s" 2>/dev/null)" != "0" ] && { tail -6 "$W/o_${name}.$s"|sed 's/^/    /'|tee -a "$RES"; break; }; done; }
  python3 - "$prog" "$NCPU" "$name" "$lev" "$RANK" <<'PY' 2>&1 | tee -a "$RES"
import sys,math
prog,nc,name,lev,rankf=sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5]
a=d=b=0
for s in range(nc):
    try:
        last=[l for l in open(f"{prog}.{s}") if l.startswith("RESULT")][-1]
        _,x,y,z=last.split(); a+=int(x);d+=int(y);b+=int(z)
    except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
verd='GAGNE (paie hors-IC)' if lo>0.5 else ('PERD hors-IC' if hi<0.5 else 'parite (IC contient 0.5)')
print(f"  {name:12s} games={g:4d} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.4f},{hi:.4f}]  => {verd}")
open(rankf,"a").write(f"{r:.4f}\t{1.96*se:.4f}\t{elo:+.0f}\t{name}\t{lev}\n")
PY
}
for e in "${ARMS[@]}"; do run_arm "${e%%|*}" "${e#*|}"; done
say ""; say "=== CLASSEMENT (score-rate vs baseline ere-gen1 ; >0.5 hors-IC = paie en force) ==="
sort -rn "$RANK" | awk -F'\t' '{printf "  %6.4f +-%.4f  elo~%s  %-12s  %s\n",$1,$2,$3,$4,$5}' | tee -a "$RES"
say "  => corner hors-IC>0.5 : premier levier search qui paie => baker. Sinon : referme la phase EBF, retour eval."
say "=== fin confirmation coin ==="
# commit job-side RESULTS + RANKING (robuste au bug runner)
commit_to_main "$RES"  "$ARTREL/RESULTS.txt" "corner-confirm 0561: RESULTS job-side (robuste runner)" && say "  RESULTS committe job-side" || say "  ⚠ commit RESULTS echoue"
commit_to_main "$RANK" "$ARTREL/RANKING.txt" "corner-confirm 0561: RANKING job-side"                  || true
