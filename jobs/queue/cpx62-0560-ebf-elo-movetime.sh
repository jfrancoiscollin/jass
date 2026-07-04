#!/usr/bin/env bash
# id: cpx62-0560-ebf-elo-movetime
# description: CONFIRMATION Elo TEMPS FIXE des leviers EBF (JFC "Go"). Le DOE 0559 (node-EBF a prof. fixe) a nomme
# probcut (economiseur sur, detection-neutre) et REJETE le NMP par la guarde-detection FIXE — mais le NMP echange de
# la detection-par-profondeur contre PLUS DE PROFONDEUR a temps fixe, donc il faut le juger au MOVETIME. Baseline =
# config ERE-GEN1 (qs_threat_ext=0, la plus forte de gen1). Bras (search-params-a) vs baseline (search-params-b) :
#   probcut  : +probcut_min_depth=5
#   nmp      : +eg_no_nmp=0 (NMP re-active, sound via F1)
#   corner   : +probcut=5,lmr_asym nonpv=2,multicut=4 (le coin DOE)
#   corner+nmp
# movetime 0.3s, dilf, SE ajustee nulles. Eval=gen1. Un bras >0.5 hors-IC => le levier paie en force au temps reel.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0560-ebf-elo-movetime/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
RANK="$ART/RANKING.txt"; : > "$RANK"
W=/root/cw-ebfelo; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen; MT=0.3; PAIRS=1; MAXPLIES=180
BASE="qs_threat_ext=0"   # config ere-gen1 (la plus forte de gen1)

say "=== build jass depuis main (archi complete) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
say "  baseline = ERE-GEN1 ($BASE) ; movetime ${MT}s ; eval gen1"

ARMS=(
  "probcut|probcut_min_depth=5"
  "nmp|eg_no_nmp=0"
  "corner|probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4"
  "corner+nmp|probcut_min_depth=5,lmr_first_full_nonpv=2,multicut_min_depth=4,eg_no_nmp=0"
)
run_arm(){ local name="$1" lev="$2"; local prog="$ART/prog_${name}"
  say ""; say "=== BRAS ${name}  (A=$BASE,$lev  vs  B=$BASE)  @ mt${MT}s dilf ==="
  for s in $(seq 0 $((NCPU-1))); do
    ( python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen1.pjtw" \
        --jass-b "$J" --pattern-b "$W/gen1.pjtw" --movetime "$MT" --pairs "$PAIRS" \
        --max-plies "$MAXPLIES" --shard "$s" --nshards "$NCPU" --quiet --openings-file "$DILF" \
        --search-params-a "$BASE,$lev" --search-params-b "$BASE" \
        --progress-file "${prog}.$s" >"$W/o_${name}.$s" 2>&1 ) &
  done; wait
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
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo=r-1.96*se
print(f"  {name:12s} games={g:4d} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  {'GAGNE' if lo>0.5 else 'parite/perd'}")
open(rankf,"a").write(f"{r:.4f}\t{1.96*se:.4f}\t{elo:+.0f}\t{name}\t{lev}\n")
PY
}
for e in "${ARMS[@]}"; do run_arm "${e%%|*}" "${e#*|}"; done
say ""; say "=== CLASSEMENT (score-rate vs baseline ere-gen1 ; >0.5 hors-IC = paie en force) ==="
sort -rn "$RANK" | awk -F'\t' '{printf "  %6.4f +-%.4f  elo~%s  %-12s  %s\n",$1,$2,$3,$4,$5}' | tee -a "$RES"
say "  => le(s) bras gagnant(s) => baker au JEU. (Ensuite : re-tester threat_ext=1 sur le coin gagnant.)"
say "=== fin confirmation EBF movetime ==="
