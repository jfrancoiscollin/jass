#!/usr/bin/env bash
# id: cpx62-0601-ordering-scanpure-confirm
# description: HEAD-TO-HEAD (JFC) — ordering "façon SCAN PUR" vs le NÔTRE actuel, en A/B Elo haut-N. Le vrai Scan pur =
# hist_mode=1,hist_pure=1,hist_order_captures=1 (EMA probabiliste sort.cpp + captures triées par history, SANS killers/
# countermove/conthist — exactement l'ordering de Scan). Side A = Scan-pur, side B = legacy (notre ordering actuel, defaut,
# byte-identical prouve). ~1200 games/cellule (SE~0.014). Deux jeux d'openings : DILF + GENERALISTE (>=38 pieces du corpus).
# mt 0.1 + 0.3. Complete 0600 (qui testait P1nc = Scan SANS E3). GATE : rate_A>0.5 hors-IC DILF ET generaliste => l'ordering
# Scan-pur bat le notre => BAKE. Sinon (neutre) => parite d'ordering confirmee (notre fmc deja 0.91, cf 0599) => front CLOS.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0601-ordering-scanpure-confirm/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0601-ordering-scanpure-confirm/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-scanpure; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
SPEC="hist_mode=1,hist_pure=1,hist_order_captures=1"; PAIRS=5; NOPEN=120

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== head-to-head Scan-pur ($SPEC) vs legacy — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/search.cpp > src/search.cpp
git show origin/develop:src/search_params.hpp > src/search_params.hpp
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/search.cpp src/search_params.hpp; exit 6; }
J="$W/build/jass"; git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null || true
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/dilf.fen"

git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if pc>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n")
print(f"  generaliste : {len(out)} openings >=38 pieces (hors-dilf)")
PY
say "  build OK ; dilf=$(wc -l<"$W/dilf.fen") gen=$(wc -l<"$W/gen.fen") ; ~$((NOPEN*PAIRS*2)) games/cellule"

ab(){ local set="$1" openf="$2" mt="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen1.pjtw" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$mt" --search-params-a "$SPEC" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"$W/x_${set}_${mt}.$s" 2>&1 & done; wait
  python3 - "$set" "$mt" "$W"/x_${set}_${mt}.* <<'PY' 2>&1 | tee -a "$RES"
import sys,math; st,mt=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
print(f"  [{st} mt{mt}] A(Scan-pur)={a} B(legacy)={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}")
PY
  rm -f "$W"/x_${set}_${mt}.* ; }
say ""; say "=== A/B Scan-pur vs legacy (haut-N) ==="
for mt in 0.1 0.3; do ab dilf "$W/dilf.fen" "$mt"; ab gen "$W/gen.fen" "$mt"; done
say ""
say "  GATE : rate_A>0.5 hors-IC DILF ET generaliste => ordering Scan-pur bat le notre => BAKE."
say "  neutre => parite d'ordering (notre fmc deja 0.91, 0599) => front ordering CLOS. (0600 fait le meme test SANS E3.)"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0601 head-to-head Scan-pur (prob+E3) vs legacy haut-N, dilf+generaliste mt0.1/0.3" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin head-to-head scan-pur ==="
