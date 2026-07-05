#!/usr/bin/env bash
# id: ccx33-0603-qs-on-ordering
# description: CO-ADAPTATION (JFC) — l'ordering prob-pur bake (hist_mode=1,hist_pure=1, +20..+43, node-EBF -8%@d12) rouvre-t-il
# la porte a la quiescence forcing/promo que 0593 avait rejetee au movetime (-92..-161, cout-noeud) ? Precedent : threat_ext
# -21 -> +108 sur la config coin (EBF reduit). On re-joue les variantes qs CONTRE LE NOUVEAU DEFAUT (main a deja le bake =>
# les 2 cotes ont l'ordering prob-pur ; side A ajoute la qs) => isole la qs PAR-DESSUS la meilleure recherche. Si une cellule
# rate_A>0.5 hors-IC => la qs co-adapte => bake. Sinon => la qs reste morte meme sur la recherche amelioree => clos. mt0.1+0.3,
# dilf, ~740 games/cellule. Build MAIN (contient deja le bake ordering promu 9422fc02). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0603-qs-on-ordering/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0603-qs-on-ordering/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-qsord; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
PAIRS=4; NOPEN=90

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== qs sur ordering bake (co-adaptation) — HEAD main $(git log --oneline -1|cat) ==="
say "  confirme bake ordering present : $(git show origin/main:src/search_params.hpp|grep -cE 'int hist_mode  = 1|int hist_pure  = 1')/2"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/open.fen"
say "  build OK (defaut = ordering prob-pur des 2 cotes) ; ~$((NOPEN*PAIRS*2)) games/cellule"

# side A = defaut + qs override ; side B = defaut (rien) => isole la qs par-dessus l'ordering baké
CELLS=( "f6p6|qs_forcing_depth=6,qs_promo_depth=6" "f4p4|qs_forcing_depth=4,qs_promo_depth=4" "f6|qs_forcing_depth=6" )
ab(){ local tag="$1" spec="$2" mt="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen1.pjtw" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$mt" --search-params-a "$spec" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/open.fen" >"$W/x_${tag}_${mt}.$s" 2>&1 & done; wait
  python3 - "$tag" "$mt" "$W"/x_${tag}_${mt}.* <<'PY' 2>&1 | tee -a "$RES"
import sys,math; tag,mt=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="CO-ADAPTE (bake) hors-IC>0.5" if lo>0.5 else ("MORTE hors-IC<0.5" if hi<0.5 else "neutre")
print(f"  [{tag} mt{mt}] A(+qs)={a} B(defaut)={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}")
PY
  rm -f "$W"/x_${tag}_${mt}.* ; }
say ""; say "=== A/B : defaut+qs (side A) vs defaut (side B), les 2 avec ordering prob-pur baké ==="
for e in "${CELLS[@]}"; do IFS='|' read -r tag spec <<<"$e"; for mt in 0.1 0.3; do ab "$tag" "$spec" "$mt"; done; done
say ""
say "  GATE : une cellule hors-IC>0.5 => la qs co-adapte a l'ordering ameliore => bake. Sinon => qs reste morte => clos."
say "  Rappel 0593 (sur l'ancien defaut) : f6p6 -125/-119, f4p4 -92, f6 -128 (tous hors-IC<0.5)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0603 qs sur ordering bake : co-adaptation ? (qs re-testee par-dessus l'ordering prob-pur)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin qs-on-ordering ==="
