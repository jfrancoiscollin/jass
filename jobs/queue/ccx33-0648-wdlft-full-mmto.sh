#!/usr/bin/env bash
# id: ccx33-0648-wdlft-full-mmto
# description: PISTE 1 FULL (en // du screen cpx62-0648) — pipeline MMTO-LAST complet sur anchor=0.1. wdl_finetune ancré
# gen2-mmto sur 3M (calibration WDL) => wdlbase' ; puis MMTO last layer : gen-siblings --leaf-mode WS-OFF ancré wdlbase' +
# rank_finetune --leaf-pov --chunk (anchor 0.05) => candidat gen4-wdlft-mmto ; A/B vs gen2-mmto (généraliste ≥38p, mt0.2+
# mt0.3). Donne le candidat "MMTO last" bout-en-bout pendant que cpx62 screene les 3 anchors des bases nues. Outil validé
# smoke 0647. WS-OFF obligatoire. AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0648-wdlft-full-mmto/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0648-wdlft-full-mmto/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-wdlft-full; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-wdlftfull
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
WDL_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/wdl-cpx62.jnnw.gz
WDL_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/wdl-ccx33.jnnw.gz
PP_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/prefs-parents-cpx62.jnnw.gz
PM_CPX=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/prefs-moves-cpx62.bin.gz
PP_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/prefs-parents-ccx33.jnnw.gz
PM_CCX=jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts/prefs-moves-ccx33.bin.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
WDLFT_ANCHOR=0.1; CHUNK_WDL=1000000; MAXIT_WDL=25
LEAFD=5; MAXPP=16; WS_OFF=-1000000000; LAM=0.3; RANK_ANCHOR=0.05; CHUNK_RANK=500000; MAXIT_RANK=60
NOPEN=96; PAIRS=8

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== PISTE 1 FULL (MMTO-last, anchor=$WDLFT_ANCHOR) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py pattern_jass/tools/train_stream.py pattern_jass/tools/wdl_finetune.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }

# ---- merge WDL 3M + dump ----
git show "origin/main:$WDL_CPX" | gunzip > "$W/wdl_cpx.jnnw"; git show "origin/main:$WDL_CCX" | gunzip > "$W/wdl_ccx.jnnw"
python3 - "$W/wdl.jnnw" "$W/wdl_cpx.jnnw" "$W/wdl_ccx.jnnw" <<'PY'
import struct,sys
outp=sys.argv[1]; REC=38; body=bytearray(); tot=0
for f in sys.argv[2:]:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  ✓ build+geom(NP=$NP)+gen2 ; WDL mergé = $N_WDL"
[ "$N_WDL" -gt 1000000 ] 2>/dev/null || { say "ABORT WDL < 1M"; restore_src; exit 7; }
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/wdlfeat.log" 2>&1 || { say "DUMP wdlfeat FAIL"; restore_src; exit 8; }

# ---- (1) wdl_finetune ancré gen2-mmto ----
say ""; say "=== (1) wdl_finetune ancré gen2-mmto anchor=$WDLFT_ANCHOR (chunk $CHUNK_WDL, iter $MAXIT_WDL) ==="
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/gen2.pjtw" --data "$W/wdl.jnnw" --feat "$W/wdlfeat" --out "$W/wdlbase.pjtw" \
    --tools pattern_jass/tools --anchor "$WDLFT_ANCHOR" --logit-scale 1.0 --chunk "$CHUNK_WDL" --max-iter "$MAXIT_WDL" \
    --full-fold --tempo-stage --verify-jass "$J" --verify-n 60 >"$W/wdlft.log" 2>&1 || { say "WDLFT FAIL"; tail -12 "$W/wdlft.log"|sed 's/^/  /'; restore_src; exit 9; }
say "  $(grep -iE 'fit : logloss|mean|POV gate' "$W/wdlft.log" | tr '\n' ' ')"
gzip -c "$W/wdlbase.pjtw" > "$ART/wdlbase-a$(echo "$WDLFT_ANCHOR"|tr '.' 'p').pjtw.gz"
commit_to_main "$ART/wdlbase-a$(echo "$WDLFT_ANCHOR"|tr '.' 'p').pjtw.gz" "$ARTREL/wdlbase-a$(echo "$WDLFT_ANCHOR"|tr '.' 'p').pjtw.gz" "0648full wdlbase ancré gen2 anchor=$WDLFT_ANCHOR" >/dev/null 2>&1 || true
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648full progress : wdlbase fitté" >/dev/null 2>&1 || true

# ---- merge prefs 2-box ----
git show "origin/main:$PP_CPX" | gunzip > "$W/pp_cpx.jnnw"; git show "origin/main:$PM_CPX" | gunzip > "$W/pm_cpx.bin"
git show "origin/main:$PP_CCX" | gunzip > "$W/pp_ccx.jnnw"; git show "origin/main:$PM_CCX" | gunzip > "$W/pm_ccx.bin"
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W/pp_cpx.jnnw" "$W/pm_cpx.bin" "$W/pp_ccx.jnnw" "$W/pm_ccx.bin" <<'PY'
import struct,sys
parout,movout=sys.argv[1],sys.argv[2]; REC=38; pairs=sys.argv[3:]
pbody=bytearray(); mbody=bytearray(); tot=0
for i in range(0,len(pairs),2):
    pb=open(pairs[i],'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; mb=open(pairs[i+1],'rb').read()
    assert len(mb)==2*n, f"align {pairs[i]}"
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody)); open(movout,'wb').write(bytes(mbody))
print(tot)
PY
N_PAR=$(jnnw_count "$W/parents.jnnw"); say "  prefs mergés = $N_PAR parents"

# ---- (2) MMTO last : gen-siblings --leaf-mode WS-OFF ancré wdlbase' + rank_finetune ----
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
say ""; say "=== (2) MMTO last : gen-siblings --leaf-mode WS-OFF ancré wdlbase' (d$LEAFD) + rank_finetune anchor=$RANK_ANCHOR ==="
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
N_PAIRS=$(( $(jnnw_count "$W/pairs.jnnw") / 2 )); say "  MMTO paires = $N_PAIRS"
[ "$N_PAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT paires ($N_PAIRS)"; restore_src; exit 10; }
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/pairfeat" >"$W/pairfeat.log" 2>&1 || { say "DUMP pairfeat FAIL"; restore_src; exit 10; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
    --champion "$W/wdlbase.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/pairfeat" --out "$W/gen4.pjtw" \
    --tools pattern_jass/tools --lam "$LAM" --anchor "$RANK_ANCHOR" --min-pairs 5 --rank-scale 1.0 --max-iter "$MAXIT_RANK" \
    --chunk "$CHUNK_RANK" --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/rank.log" 2>&1 || { say "RANK FAIL"; tail -12 "$W/rank.log"|sed 's/^/  /'; restore_src; exit 11; }
say "  $(grep -E 'pairwise-acc|delta' "$W/rank.log" | tr '\n' ' ')"
[ -s "$W/gen4.pjtw" ] || { say "ABORT gen4 absent"; restore_src; exit 11; }
gzip -c "$W/gen4.pjtw" > "$ART/gen4-wdlft-mmto.pjtw.gz"
commit_to_main "$ART/gen4-wdlft-mmto.pjtw.gz" "$ARTREL/gen4-wdlft-mmto.pjtw.gz" "0648full candidat gen4-wdlft-mmto (MMTO last ancré wdlbase')" >/dev/null 2>&1 || true

# ---- openings ≥38p ----
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
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 10 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 12; }

# ---- (3) A/B gen4 vs gen2-mmto (mt0.2 + mt0.3) ----
say ""; say "=== (3) A/B gen4-wdlft-mmto vs gen2-mmto (généraliste) ==="
abcell(){ local mt="$1"; local pref="$W/ab_$mt"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen4.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$mt" "$W/.about" "${pref}".* <<'PY'
import sys,math
mt,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [gen4-wdlft-mmto vs gen2-mmto | generaliste mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.about" | tee -a "$RES"; rm -f "${pref}".* ; }
abcell 0.2
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648full A/B gen4 mt0.2" >/dev/null 2>&1 || true
abcell 0.3
restore_src
say ""; say "  GATE : gen4-wdlft-mmto >0.5 hors-IC => le pipeline MMTO-last sur base WDL-calibrée-ancrée AJOUTE sur gen2-mmto => confirm dilf + d9-vs-Scan + bake."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0648full FIN : gen4-wdlft-mmto (MMTO last, anchor $WDLFT_ANCHOR) vs gen2-mmto" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin piste 1 full ==="
