#!/usr/bin/env bash
# id: cpx62-0646-couplage-fit-ab
# description: COUPLAGE Phase-A — FIT + A/B. Consomme le self-play 0645 (2 box) : ~3M positions WDL (mix BAL+ASYM) + ~323k
# prefs MMTO. Pipeline : merge 2 corpus -> fit WDL FRAIS (train_stream --target wdl --color-fold --tempo-stage --l2 3e-5
# --chunk 1M, gradient exact streamé) = wdlbase -> MMTO gen-siblings --leaf-mode WS-OFF ancré wdlbase -> rank_finetune
# --leaf-pov --chunk (streamé) SWEEP anchor {0, 0.01, 0.05} = 3 candidats gen3-wdlmmto -> A/B chaque candidat vs gen2-mmto
# (généraliste ≥38p, mt0.2, arch fixé filtre-vides). Cellules + candidats committés AU FIL. GATE : un candidat >0.5 hors-IC
# => le couplage AJOUTE sur gen2-mmto => on confirme (mt0.3+dilf) + d9-vs-Scan. WS-OFF obligatoire (0641 WS-ON=-354). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0646-couplage-fit-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0646-couplage-fit-ab/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-cpl-fit; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-cplfit
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
WDL_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/wdl-cpx62.jnnw.gz
WDL_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/wdl-ccx33.jnnw.gz
PP_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/prefs-parents-cpx62.jnnw.gz
PM_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/prefs-moves-cpx62.bin.gz
PP_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/prefs-parents-ccx33.jnnw.gz
PM_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/prefs-moves-ccx33.bin.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
# --- fit params (recette champion éprouvée) ---
L2=3e-5; MAXIT_WDL=25; CHUNK_WDL=1000000
LEAFD=5; MAXPP=16; WS_OFF=-1000000000; LAM=0.3; CHUNK_RANK=500000; MAXIT_RANK=60
ANCHORS="0 0.01 0.05"
# --- A/B params ---
NOPEN=96; PAIRS=8; ABMT=0.2

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== COUPLAGE Phase-A FIT+A/B — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py pattern_jass/tools/train_stream.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
say "  ✓ build+geom (NP=$NP) + gen2-mmto"

# ---- merge WDL corpus (cpx62 + ccx33) ----
git show "origin/main:$WDL_CPX" | gunzip > "$W/wdl_cpx.jnnw"
git show "origin/main:$WDL_CCX" | gunzip > "$W/wdl_ccx.jnnw"
python3 - "$W/wdl.jnnw" "$W/wdl_cpx.jnnw" "$W/wdl_ccx.jnnw" <<'PY'
import struct,sys
outp=sys.argv[1]; REC=38; body=bytearray(); tot=0
for f in sys.argv[2:]:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  WDL corpus mergé (2 box) = $N_WDL positions"
[ "$N_WDL" -gt 1000000 ] 2>/dev/null || { say "ABORT WDL corpus < 1M ($N_WDL)"; restore_src; exit 7; }

# ---- merge prefs (parents JNNW + moves 2B) alignés, cpx62 puis ccx33 ----
git show "origin/main:$PP_CPX" | gunzip > "$W/pp_cpx.jnnw"; git show "origin/main:$PM_CPX" | gunzip > "$W/pm_cpx.bin"
git show "origin/main:$PP_CCX" | gunzip > "$W/pp_ccx.jnnw"; git show "origin/main:$PM_CCX" | gunzip > "$W/pm_ccx.bin"
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W/pp_cpx.jnnw" "$W/pm_cpx.bin" "$W/pp_ccx.jnnw" "$W/pm_ccx.bin" <<'PY'
import struct,sys
parout,movout=sys.argv[1],sys.argv[2]; REC=38; pairs=sys.argv[3:]
pbody=bytearray(); mbody=bytearray(); tot=0
for i in range(0,len(pairs),2):
    pb=open(pairs[i],'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; mb=open(pairs[i+1],'rb').read()
    assert len(mb)==2*n, f"align {pairs[i]}: moves {len(mb)} != 2*{n}"
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody)); open(movout,'wb').write(bytes(mbody))
print(tot)
PY
N_PAR=$(jnnw_count "$W/parents.jnnw"); say "  prefs mergés (2 box) = $N_PAR parents"

# ---- (1) fit WDL FRAIS streamé exact ----
say ""; say "=== (1) fit WDL frais : train_stream --target wdl --color-fold --l2 $L2 (chunk $CHUNK_WDL, iter $MAXIT_WDL) sur $N_WDL ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/wdlfeat.log" 2>&1 || { say "DUMP wdlfeat FAIL"; tail -5 "$W/wdlfeat.log"|sed 's/^/  /'; restore_src; exit 8; }
env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/wdl.jnnw" --feat "$W/wdlfeat" \
    --target wdl --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT_WDL" --chunk "$CHUNK_WDL" \
    --out "$W/wdlbase.pjtw" >"$W/wdlfit.log" 2>&1 || { say "TRAIN WDL FAIL"; tail -15 "$W/wdlfit.log"|sed 's/^/  /'; restore_src; exit 9; }
grep -iE 'target=wdl|train.?loss|wrote' "$W/wdlfit.log" | tail -3 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/wdlbase.pjtw" > "$ART/wdlbase.pjtw.gz"
commit_to_main "$ART/wdlbase.pjtw.gz" "$ARTREL/wdlbase.pjtw.gz" "0646 wdlbase (fit WDL frais 3M mix)" >/dev/null 2>&1 || true
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0646 progress : wdlbase fitté" >/dev/null 2>&1 || true

# ---- (2) MMTO gen-siblings --leaf-mode WS-OFF ancré wdlbase ----
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi: open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC]); open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
PY
say ""; say "=== (2) MMTO gen-siblings --leaf-mode WS-OFF (ancre=wdlbase, d$LEAFD) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WS_OFF" --nnue "$W/wdlbase.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_PAIRS=$(( $(jnnw_count "$W/pairs.jnnw") / 2 )); say "  MMTO paires (feuilles-PV, WS-OFF) = $N_PAIRS"
[ "$N_PAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT paires ($N_PAIRS)"; restore_src; exit 10; }
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/pairfeat" >"$W/pairfeat.log" 2>&1 || { say "DUMP pairfeat FAIL"; restore_src; exit 10; }

# ---- (3) rank_finetune SWEEP anchor {0,0.01,0.05} ancré wdlbase ----
say ""; say "=== (3) rank_finetune --leaf-pov --chunk $CHUNK_RANK, SWEEP anchor {$ANCHORS} (ancre=wdlbase) ==="
declare -A CANDPATH
for A in $ANCHORS; do
  tag=$(echo "$A" | tr '.' 'p')
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/wdlbase.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/pairfeat" --out "$W/cand_$tag.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter "$MAXIT_RANK" \
      --chunk "$CHUNK_RANK" --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/rank_$tag.log" 2>&1
  if [ $? = 0 ] && [ -s "$W/cand_$tag.pjtw" ]; then
    CANDPATH[$A]="$W/cand_$tag.pjtw"
    D=$(grep -E 'pairwise-acc|delta' "$W/rank_$tag.log" | tr '\n' ' ')
    say "  [anchor=$A] $D"
    gzip -c "$W/cand_$tag.pjtw" > "$ART/gen3-wdlmmto-a$tag.pjtw.gz"
    commit_to_main "$ART/gen3-wdlmmto-a$tag.pjtw.gz" "$ARTREL/gen3-wdlmmto-a$tag.pjtw.gz" "0646 candidat gen3-wdlmmto anchor=$A" >/dev/null 2>&1 || true
  else say "  [anchor=$A] FIT FAIL : $(tail -2 "$W/rank_$tag.log"|tr '\n' ' ')"; fi
done
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0646 progress : candidats gen3-wdlmmto fittés (sweep anchor)" >/dev/null 2>&1 || true
[ "${#CANDPATH[@]}" -gt 0 ] || { say "ABORT aucun candidat"; restore_src; exit 11; }

# ---- openings généralistes ≥38p (signal), arch fixé ----
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
NG=$(grep -c . "$W/gen.fen"); say "  openings généralistes ≥38p : $NG"
[ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 12; }

# ---- (4) A/B chaque candidat vs gen2-mmto (généraliste mt$ABMT) ----
say ""; say "=== (4) A/B candidats gen3-wdlmmto vs gen2-mmto (généraliste mt$ABMT) ==="
abcell(){ local cand="$1" tag="$2"; local pref="$W/ab_$tag"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$cand" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$ABMT" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$tag" "$W/.about" "${pref}".* <<'PY'
import sys,math
tag,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [anchor {tag} vs gen2-mmto | generaliste mt] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.about" | tee -a "$RES"; rm -f "${pref}".* ; }
for A in $ANCHORS; do
  tag=$(echo "$A" | tr '.' 'p'); [ -n "${CANDPATH[$A]:-}" ] || continue
  abcell "${CANDPATH[$A]}" "$tag"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0646 A/B anchor=$A vs gen2-mmto (généraliste mt$ABMT)" >/dev/null 2>&1 || true
done
restore_src
say ""; say "  GATE : un candidat rate_A>0.5 hors-IC => le COUPLAGE WDL<->MMTO AJOUTE sur gen2-mmto (levier orthogonal)."
say "  => si oui : confirmer le meilleur anchor (mt0.3 + dilf) + gate d9-vs-Scan, puis bake candidat gen3-wdlmmto."
say "  => si neutre partout : le fresh-WDL-base n'ajoute pas non plus ; conclusion sur le pipeline linéaire."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0646 FIN couplage fit+A/B : le couplage ajoute-t-il sur gen2-mmto (sweep anchor)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin couplage fit+A/B ==="
