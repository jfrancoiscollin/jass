#!/usr/bin/env bash
# id: cpx62-0661-qs-movetime
# description: TEST MOVETIME de la quiescence forte (suite 0660). 0660 : à prof fixe d9, qs6 (qs_forcing=6,qs_promo=6) AJOUTE
# +84 Elo en self-play vs default (gen2-mmto) — mais le déficit vs Scan ne se ferme pas. Question décisive : ce +84 fixed-depth
# SURVIT-IL au MOVETIME (0593 disait qu'il mourait avec l'ancienne éval : la qs profonde coûte du temps -> moins de noeuds ->
# gain évaporé) ou gen2 co-adapte ? A/B self-play gen2 (A=qs fort, B=default), mt0.2 + mt0.3, généraliste. Harnais durci
# (per-game try/except -> nulle) + timeout x5 (develop) = overshoot endgame géré. GATE : qs fort >0.5 hors-IC à mt => gain
# search BAKEABLE (gratuit). Neutre/pire => meurt au mt (résidu = vitesse NPS -134). AUCUN NNUE. gen2 reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0661-qs-movetime/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0661-qs-movetime/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-qs-mt; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
NOPEN=64; PAIRS=12
QS6="qs_forcing_depth=6,qs_promo_depth=6"
QSMAX="qs_forcing_depth=6,qs_promo_depth=6,qs_threat_ext=1,qs_sacs=1"
# cellules : "nom:mt:params"
CELLS=( "qs6_mt02:0.2:$QS6" "qs6_mt03:0.3:$QS6" "qsmax_mt03:0.3:$QSMAX" )

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== TEST MOVETIME quiescence gen2-mmto (le +84 fixed-depth survit-il ?) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
restore_src(){ git checkout -- src/main.cpp tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0661 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    Bl=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG ; build+gen2 ✓ (harnais durci + timeout x5)"; [ "$NG" -gt 20 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }

mtcell(){ local name="$1" mt="$2" sp="$3"; local pref="$W/mt_$name"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" --search-params-a "$sp" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$name" "$mt" "$sp" "$W/.mt" "${pref}".* <<'PY'
import sys,math
name,mt,sp,outp=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]; a=d=b=0
for f in sys.argv[5:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; se=(0.5/(g**0.5)) if g else 1
elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
vd="qs fort SURVIT au mt (AJOUTE hors-IC)" if lo>0.5 else ("qs fort MEURT/PERD hors-IC" if hi<0.5 else "neutre au mt")
open(outp,'w').write(f"  [self-play mt{mt} | {name:10s} qsA vs default | {sp:52s}] A={a} B={b} D={d} n={g} rate_A={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f} => {vd}\n")
PY
  cat "$W/.mt" | tee -a "$RES"; }

say ""; say "=== A/B self-play movetime (qs fort A vs default B, même éval gen2) ==="
for cell in "${CELLS[@]}"; do
  IFS=':' read -r name mt sp <<< "$cell"
  mtcell "$name" "$mt" "$sp"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0661 $name" >/dev/null 2>&1 || true
done
restore_src
say ""; say "  GATE : qs fort rate_A>0.5 hors-IC à mt => le +84 fixed-depth SURVIT au movetime => gain search BAKEABLE (intégrer au champion)."
say "  neutre/pire => la qs profonde meurt au mt (coût-temps, 0593 re-confirmé avec gen2) => le résidu movetime est la VITESSE (NPS -134), pas la qs."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0661 FIN test movetime qs : le +84 fixed-depth survit-il au mt" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin test movetime qs ==="
