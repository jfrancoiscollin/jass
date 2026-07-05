#!/usr/bin/env bash
# id: cpx62-0593-qs-movetime
# description: MANCHE SEARCH (suite 0592) — 0592 a localise le deficit par-noeud dans la QUIESCENCE : ajouter forcing+promo
# qs (qs_forcing_depth=6,qs_promo_depth=6) HALVE le gap fixed-depth vs Scan (-335 -> -175 a d9). Reste LA question : ca paie
# au TEMPS REEL ? (la qs coute des noeuds => moins de profondeur ; le +160 fixed-depth doit survivre). Test = jass-vs-jass
# A/B au MOVETIME, side A = variante qs, side B = coin bake (spec vide), gen1 des 2 cotes, meme build => mesure PURE du
# trade-off precision-feuille vs profondeur. Sweep : sweet-spot (f6p6 / f4p4 / f6-seul) @ mt0.2 + robustesse TC du gagnant
# 0592 (f6p6) @ mt0.05 et mt0.5. GATE : side A rate>0.5 hors-IC => la qs paie a temps reel => BAKE (3e gain search apres
# coin +49, threat_ext +108). NB jass-vs-jass = contention-robuste pour l'Elo RELATIF (les 2 cotes subissent la meme
# charge). qs_threat_ext deja bake ON ; ici on AJOUTE forcing+promo qs (distincts). AUCUN NNUE, recherche mesuree.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0593-qs-movetime/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0593-qs-movetime/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-qsmt; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
PAIRS=4; NOPEN=80   # 80*4*2 = 640 games/cellule, shardé sur NCPU

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== qs-movetime (suite 0592) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/open.fen"
say "  eval=gen1 (2 cotes) ; moteur coin=$(git show origin/main:src/search_params.hpp|grep -cE 'probcut_min_depth = 5|qs_threat_ext = true|lmr_first_full_nonpv = 2')/3 ; ~$((NOPEN*PAIRS*2)) g/cellule ; side B=coin (spec vide)"

# cellule : tag|movetime|spec_side_A
CELLS=(
  "f6p6_mt02|0.2|qs_forcing_depth=6,qs_promo_depth=6"
  "f4p4_mt02|0.2|qs_forcing_depth=4,qs_promo_depth=4"
  "f6_mt02|0.2|qs_forcing_depth=6"
  "f6p6_mt005|0.05|qs_forcing_depth=6,qs_promo_depth=6"
  "f6p6_mt05|0.5|qs_forcing_depth=6,qs_promo_depth=6"
)
run_cell(){ local tag="$1" mt="$2" spec="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
      --jass-a "$J" --pattern-a "$W/gen1.pjtw" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
      --movetime "$mt" --search-params-a "$spec" --pairs "$PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/open.fen" \
      >"$W/${tag}.$s" 2>&1 & done; wait
  python3 - "$tag" "$mt" "$spec" "$W"/${tag}.* <<'PY' 2>&1 | tee -a "$RES"
import sys,math; tag,mt,spec=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="PAIE (bake) — hors-IC>0.5" if lo>0.5 else ("NUIT — hors-IC<0.5" if hi<0.5 else "NEUTRE (IC contient 0.5)")
print(f"  [{tag}] mt={mt} A(qs)={a} B(coin)={b} D={d} n={g}  rate_A={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.3f},{hi:.3f}]  => {vd}  ({spec})")
PY
  rm -f "$W"/${tag}.* ; }

say ""; say "=== A/B jass-vs-jass au MOVETIME (side A=qs vs side B=coin, gen1) ==="
for e in "${CELLS[@]}"; do IFS='|' read -r tag mt spec <<<"$e"; say "  -- $tag (mt=$mt : $spec) --"; run_cell "$tag" "$mt" "$spec"; done
say ""
say "  GATE : une cellule rate_A>0.5 hors-IC => la quiescence forcing/promo PAIE au temps reel => BAKE le meilleur spec"
say "  (3e gain search). Si NEUTRE partout => le +160 fixed-depth ne survit pas au cout-noeud => la qs ne change pas la"
say "  force reelle (le pruning nous redonne la profondeur perdue) => rester sur les autres leviers search/EBF."
say "  Robustesse TC : comparer f6p6 @ mt0.05 / 0.2 / 0.5 (si le gain croit avec le temps => qs + profondeur composent)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0593 qs-movetime : forcing/promo quiescence paie-t-elle au temps reel (bake gate) ?" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin qs-movetime ==="
