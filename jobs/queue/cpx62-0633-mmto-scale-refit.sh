#!/usr/bin/env bash
# id: cpx62-0633-mmto-scale-refit
# description: RE-FIT du gros corpus 0630 (scale équilibré, le fit OOM'a sur ccx33 avec 3.5M paires). Ici sur cpx62 (+RAM),
# 308k parents équilibrés sous-échantillonnés à 120k + maxpp=8 => ~1M paires (mémoire-safe). Teste enfin LE PAYOFF DU VOLUME :
# 120k positions équilibrées (contestées) bat-il le +52 de la boucle externe / +47 one-shot ? MMTO --leaf-mode --leaf-pov
# (une passe, ancre gen1), puis A/B généraliste(signal)+dilf(garde-fou) mt0.2+0.3. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0633-mmto-scale-refit/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0633-mmto-scale-refit/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-refit; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-refit
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
PAR_GZ=jobs/results/ccx33-0630-mmto-scan-mixed-highvol/artefacts/scan-mixed-parents.jnnw.gz
MOV_GZ=jobs/results/ccx33-0630-mmto-scan-mixed-highvol/artefacts/scan-mixed-moves.bin.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LEAFD=5; MAXPP=8; LAM=0.3; ANCHOR=0.05; WSOFF=-1000000000; NITERS=1; NOPEN=96; PAIRS=8; SUBSAMPLE=120000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== BOUCLE EXTERNE MMTO — HEAD main $(git log --oneline -1|cat) ==="
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
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$PAR_GZ" | gunzip > "$W/parents_full.jnnw" || { say "ABORT parents"; exit 4; }
git show "origin/main:$MOV_GZ" | gunzip > "$W/moves_full.bin" || { say "ABORT moves"; exit 4; }
# sous-échantillonnage mémoire-safe : garder SUBSAMPLE parents répartis (pas=n/SUBSAMPLE), moves alignés
python3 - "$W/parents_full.jnnw" "$W/moves_full.bin" "$W/parents.jnnw" "$W/moves.bin" "$SUBSAMPLE" <<'PY'
import struct,sys
pf,mf,po,mo,K=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
idx=range(n) if n<=K else [int(i*(n/float(K))) for i in range(K)]
pbody=bytearray(); mbody=bytearray()
for i in idx:
    pbody+=body[i*REC:(i+1)*REC]; mbody+=mb[i*2:i*2+2]
open(po,'wb').write(b'JNNW'+struct.pack('<I',len(mbody)//2)+bytes(pbody)); open(mo,'wb').write(bytes(mbody))
print(f"  sous-échantillon : {n} -> {len(mbody)//2}")
PY
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  ✓ corpus 0630 équilibré sous-éch. parents=$NPAR ; anchor=$ANCHOR maxpp=$MAXPP"

# split parents+moves une fois (fixe sur toute la boucle)
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

PREV="$W/gen1.pjtw"
for it in $(seq 1 $NITERS); do
  say ""; say "=== ITÉRATION $it : feuilles depuis $(basename "$PREV") → fit (ancre gen1) ==="
  for s in $(seq 0 $((NCPU-1))); do
    "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
         --leaf-mode --ws-margin "$WSOFF" --nnue "$PREV" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
  done; wait
  python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  it pairs : {tot//2}")
PY
  NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
  "$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump_$it.log" 2>&1 || { say "DUMP FAIL it$it"; exit 9; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/cand_$it.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$ANCHOR" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 40 >"$W/ft_$it.log" 2>&1
  if [ $? != 0 ]; then say "  it$it fit ABORT : $(tail -2 "$W/ft_$it.log"|tr '\n' ' ')"; break; fi
  ACC=$(grep -oE 'pairwise-acc [0-9.]+->[0-9.]+ \(delta [-+0-9.]+\)' "$W/ft_$it.log" | tail -1)
  say "  it$it : paires=$NPAIRS ; $ACC"
  gzip -c "$W/cand_$it.pjtw" > "$ART/cand_it$it.pjtw.gz"
  commit_to_main "$ART/cand_it$it.pjtw.gz" "$ARTREL/cand_it$it.pjtw.gz" "0632 boucle externe MMTO candidat it$it" >/dev/null 2>&1 || true
  PREV="$W/cand_$it.pjtw"
done
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null || true
FINAL="$PREV"; [ "$FINAL" = "$W/gen1.pjtw" ] && { say "  aucune itération réussie"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0632 boucle externe : aucune iter"; exit 0; }
say ""; say "  => convergence : pré-fit pairwise-acc doit MONTER et delta RÉTRÉCIR à travers it1→it$NITERS."

# ---- A/B cand final vs gen1 (généraliste=signal, dilf=garde-fou, mt0.2+0.3) ----
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
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
cell(){ local oset="$1" openf="$2" mt="$3"; local pref="$W/x_${oset}_${mt}"
  rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$FINAL" --jass-b "$J" --pattern-b "$W/gen1.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 \
    --shard "$s" --nshards "$NCPU" --quiet --openings-file "$openf" >"${pref}.$s" 2>&1 & done; wait
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
open(outp,'w').write(f"  [cand_final vs gen1 | {st} mt{mt}] A={a} B={b} D={d} n={g} rate_A={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f} IC=[{lo:.3f},{hi:.3f}] => {vd}\n")
PY
  cat "$W/.cellout" | tee -a "$RES"; rm -f "${pref}".*
}
say ""; say "=== A/B cand_final (it$NITERS) vs gen1 (généraliste=signal, dilf=garde-fou) ==="
for mt in 0.2 0.3; do
  cell gen  "$W/gen.fen"  "$mt"
  cell dilf "$W/dilf.fen" "$mt"
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0632 boucle externe A/B progrès (mt$mt)" >/dev/null 2>&1 || true
done
say ""; say "  GATE : généraliste > +52 hors-IC => le VOLUME équilibré paie => scaler + coupler (0631). ~+52 => plateau volume, le gisement est ailleurs."
say "         plateau ~+47 => one-shot suffit sur ce corpus => le gisement est dans le VOLUME/qualité data (0630/0631), pas les itérations."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0632 boucle externe MMTO : trajectoire fit + A/B cand_final (multiplicateur ou plateau)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin boucle externe ==="
