#!/usr/bin/env bash
# id: ccx33-0472-deeprelabel-flipcheck
# description: DIAGNOSTIC LEGER (demande JFC) — recupere le FLIP% perdu de 0470 (RESULTS non flushe). 0470 = deep-relabel d16 sur
# 500k positions de milieu -> 0440 PLAT (0.313, dans l'IC egdbmix). Question : le relabel a-t-il REELLEMENT change des labels
# (FLIP eleve => 0.313 plat est significatif = labels corriges mais n'aident pas en single-pass), ou est-ce un quasi NO-OP
# (FLIP faible => 0.313 ~ egdbmix attendu, rien teste) ? On ne RE-RELABEL PAS (5-6h) : le deep_sample.jnnw (500k relabelises)
# est deja committe. On RE-ECHANTILLONNE les MEMES positions (seed 20 identique a 0470) pour recuperer leurs labels SHALLOW,
# on matche par CLE (bitboards+stm) au deep_sample, et on compte FLIP% + distribution + exemples (shallow W/D -> deep L = shot
# attrape). ~15 min, pas de build jass. Eclaire 0470 et de-risque le bootstrap 0471. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0472-deeprelabel-flipcheck/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-flipcheck; rm -rf "$W"; mkdir -p "$W"
POOL_TRIM=12000000; NSAMPLE=500000; MID_LO=12; MID_HI=44; SEED=20   # IDENTIQUES a 0470
DEEP_GZ_PATH=jobs/results/ccx33-0470-deeprelabel-probe/artefacts/deep_sample.jnnw

trim(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os,shutil; REC=38
acc=sys.argv[1]; Wn=int(sys.argv[2])
with open(acc,'rb') as f:
    n=struct.unpack('<I',f.read(8)[4:8])[0]
    if n<=Wn: print(n); sys.exit(0)
    f.seek(8+(n-Wn)*REC); tmp=acc+'.t'
    with open(tmp,'wb') as o: o.write(b'JNNW'+struct.pack('<I',Wn)); shutil.copyfileobj(f,o,1<<24)
os.replace(tmp,acc); print(Wn)
PY
}

say "=== recupere le deep_sample.jnnw committe par 0470 ==="
git show "origin/main:$DEEP_GZ_PATH" > "$W/deep.jnnw" 2>/dev/null || git show "HEAD:$DEEP_GZ_PATH" > "$W/deep.jnnw" 2>/dev/null || { say "ABORT: deep_sample.jnnw (0470) introuvable"; exit 4; }
NDEEP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/deep.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  deep_sample (0470) : ${NDEEP} positions relabelisees"
[ "${NDEEP:-0}" -ge 100000 ] || { say "ABORT: deep_sample trop petit (${NDEEP})"; exit 4; }

say "=== assemble pool + re-echantillonne les MEMES positions (seed ${SEED}) pour leurs labels SHALLOW ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
python3 - "$W/pool.jnnw" "$W/shallow.jnnw" "$NSAMPLE" "$MID_LO" "$MID_HI" "$SEED" <<'PY' | tee -a "$RES"
import struct,sys,random; REC=38
pool,out,cap,lo,hi,seed=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
random.seed(seed); idx=list(range(n)); random.shuffle(idx); recs=bytearray(); cnt=0
for i in idx:
    r=bytes(body[i*REC:(i+1)*REC]); wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: recs+=r; cnt+=1
    if cnt>=cap: break
open(out,'wb').write(b'JNNW'+struct.pack('<I',cnt)+bytes(recs)); print(f"  re-echantillon shallow : {cnt} positions (seed {seed}, mid {lo}-{hi})")
PY

say "=== FLIP : matche par cle (bitboards+stm), compare shallow WDL vs deep WDL ==="
python3 - "$W/shallow.jnnw" "$W/deep.jnnw" "$ART/FLIP.txt" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
shp,dpp,flipout=sys.argv[1],sys.argv[2],sys.argv[3]
def load(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; return memoryview(b)[8:8+n*REC],n
sb,ns=load(shp); db,nd=load(dpp)
# dict cle->shallow_wdl
sh={}
for i in range(ns):
    key=bytes(sb[i*REC:i*REC+33])  # 32 bitboards + 1 stm
    sh[key]=struct.unpack('<b',sb[i*REC+37:i*REC+38])[0]
matched=flip=same=0; trans={}; dist_deep={-1:0,0:0,1:0}; examples=[]
sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
for i in range(nd):
    rec=db[i*REC:(i+1)*REC]; key=bytes(rec[:33])
    if key not in sh: continue
    matched+=1; w0=sh[key]; w1=struct.unpack('<b',rec[37:38])[0]
    dist_deep[w1]=dist_deep.get(w1,0)+1
    if w0==w1: same+=1
    else:
        flip+=1; trans[(w0,w1)]=trans.get((w0,w1),0)+1
        if w0>=0 and w1<0 and len(examples)<5:  # shallow gagnant/nul -> deep PERDANT = shot attrape
            wm,wk,bm,bk=struct.unpack('<QQQQ',rec[:32]); stm=rec[32]
            f=f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}"
            examples.append((w0,w1,f))
m=matched or 1
lines=[f"matched={matched} flip={flip} same={same} flip_pct={100*flip/m:.1f}",
       f"deep_dist L={dist_deep.get(-1,0)} D={dist_deep.get(0,0)} W={dist_deep.get(1,0)}",
       "transitions(shallow->deep): "+", ".join(f"{a:+d}->{b:+d}:{c}" for (a,b),c in sorted(trans.items(),key=lambda x:-x[1]))]
open(flipout,'w').write("\n".join(lines)+"\n")
for l in lines: print("  "+l)
print("  exemples shallow-gagnant/nul -> deep-PERDANT (shot que d16 attrape) :")
for w0,w1,f in examples: print(f"    {w0:+d}->{w1:+d}  {f}")
print("")
print("  LECTURE :")
print("   FLIP eleve (>~25%) => le relabel d16 CORRIGE beaucoup de labels => 0470 plat (0.313) = labels corriges qui")
print("        n'aident pas EN SINGLE-PASS => le bootstrap itere (0471) est bien le bon test (la correction doit s'accumuler).")
print("   FLIP faible (<~10%) => le relabel est quasi NO-OP a d16/egdbmix => 0.313~egdbmix attendu, rien teste => monter")
print("        depth (d18-20) ou desactiver l'elagage pendant le relabel pour que la recherche attrape plus de shots.")
PY
say ""; say "# FLIP committe dans artefacts/FLIP.txt (survit au non-flush de RESULTS)."
