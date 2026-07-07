#!/usr/bin/env bash
# id: cpx62-0639-mmto-conv-gen2-refit
# description: RONDE MMTO rapide sur cpx62 (libéré de 0636) — RÉUTILISE le corpus conversion Scan DÉJÀ committé (0627, 59k
# parents) SANS re-générer. Feuilles re-générées avec le NOUVEAU champion gen2-mmto (--nnue gen2-mmto), WORKING-SET ON,
# fit ancré gen2-mmto, sweep anchor {0.02, 0.05} (teste anchor→0). A/B du meilleur vs gen2-mmto (généraliste=signal +
# dilf=garde-fou). Léger (59k, pas de gen, zéro OOM) ~2h. Complément rapide de 0638 (gros corpus, ~8h). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0639-mmto-conv-gen2-refit/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0639-mmto-conv-gen2-refit/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-conv-refit; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-convr
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
PAR_GZ=jobs/results/ccx33-0627-mmto-scan-selfplay-highvol/artefacts/scan-sp-parents.jnnw.gz
MOV_GZ=jobs/results/ccx33-0627-mmto-scan-selfplay-highvol/artefacts/scan-sp-moves.bin.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LEAFD=5; MAXPP=16; LAM=0.3; WS_MARGIN=10; NOPEN=96; PAIRS=8

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RONDE MMTO conv/gen2 (refit rapide) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; exit 4; }
git show "origin/main:$PAR_GZ" | gunzip > "$W/parents.jnnw" || { say "ABORT parents 0627"; exit 4; }
git show "origin/main:$MOV_GZ" | gunzip > "$W/moves.bin" || { say "ABORT moves 0627"; exit 4; }
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  ✓ build + corpus 0627 conversion parents=$NPAR ; ancre=gen2-mmto ; WS_margin=$WS_MARGIN (ON)"

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
say ""; say "=== MMTO gen-siblings --leaf-mode (ancre gen2-mmto, WS ON, d$LEAFD) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WS_MARGIN" --nnue "$W/gen2.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
grep -h '^GENSIB' "$W"/gs_*.log | sed 's/^/  /' | tail -1 | tee -a "$RES"
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  MMTO pairs : {tot//2}")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  MMTO paires (WS, feuilles-PV gen2) : $NPAIRS"
[ "$NPAIRS" -gt 500 ] 2>/dev/null || { say "ABORT paires"; exit 8; }
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; exit 9; }
say "  dump : $(tail -1 "$W/dump.log")"

# fit sweep anchor {0.02, 0.05}
BEST=""
for A in 0.05 0.02; do
  say ""; say "=== rank_finetune ancre gen2-mmto --leaf-pov anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen2.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/cand_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"
    gzip -c "$W/cand_$A.pjtw" > "$ART/cand_a$A.pjtw.gz"
    commit_to_main "$ART/cand_a$A.pjtw.gz" "$ARTREL/cand_a$A.pjtw.gz" "0639 candidat conv/gen2 anchor=$A" >/dev/null 2>&1 || true
    [ "$A" = "0.05" ] && BEST="$W/cand_$A.pjtw"
  else say "  [$A] fit ABORT : $(tail -1 "$W/ft_$A.log")"; fi
done
[ -n "$BEST" ] || { say "ABORT : anchor 0.05 non produit"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0639 fit rate"; exit 0; }
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null || true

# openings généraliste + dilf
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
    if bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
# A/B best (anchor 0.05) vs gen2-mmto : généraliste mt0.2+0.3 (signal) + dilf mt0.3 (garde-fou)
cell(){ local oset="$1" openf="$2" mt="$3"; local pref="$W/x_${oset}_${mt}"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$BEST" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$oset" "$mt" "$W/.cellout" "${pref}".* <<'PY'
import sys,math
st,mt,outp=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else (0.5/(g**0.5) if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="GAGNE hors-IC" if lo>0.5 else ("PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [conv/gen2 a0.05 vs gen2-mmto | {st} mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".* ; }
say ""; say "=== A/B cand(anchor0.05) vs gen2-mmto — généraliste=signal + dilf=garde-fou ==="
cell gen  "$W/gen.fen"  0.2
cell gen  "$W/gen.fen"  0.3
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0639 A/B progrès (gen fait)" >/dev/null 2>&1 || true
cell dilf "$W/dilf.fen" 0.3
say ""; say "  GATE : généraliste > 0 hors-IC => la conversion-Scan ajoute sur gen2-mmto => on cumule (0638 gros corpus confirmera/amplifiera)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0639 ronde MMTO conv/gen2 : candidat + A/B (conversion ajoute-t-elle sur gen2-mmto)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin ronde conv/gen2 ==="
