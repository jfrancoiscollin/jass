#!/usr/bin/env bash
# id: ccx33-0591-a4-encoding-rankloss
# description: A4 (mini-memo, JFC "go A4") — PROBE DU PLAFOND EVAL en RANG. 0576 a sorti jass-static vs Scan-static r=0.04
# ET scan-vs-outcome=0.03 => un moteur fort NE PEUT PAS etre ~0-correle a l'issue => extraction Scan DEGENEREE (signature
# POV : score Scan probablement White-POV, notre eval STM-POV, le stm alterne => moitie des signes inverses => correl
# s'effondre). A4 : (1) DEBUG POV empirique (essaye les 2 conventions, garde celle qui maximise scan-vs-materiel &
# scan-vs-outcome) ; (2) reframe en RANG (Spearman, invariant echelle/POV) : jass-static vs Scan-static vs ORACLE d12
# (self-search, verite fiable) vs OUTCOME, GLOBAL + par phase. DECISIF (geometrie 8cf⊂32cf) : si scan-vs-oracle rho >>
# jass-vs-oracle rho => notre classe PEUT representer Scan (superset) => le retard est le FIT (E3/optim), PAS la capacite ;
# si ~= => parite eval => retard = SEARCH (valide EBF). AUCUN NNUE, AUCUNE distillation (Scan = ORACLE de MESURE, jamais
# source de label promue), recherche inchangee (pure mesure).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0591-a4-encoding-rankloss/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0591-a4-encoding-rankloss/artefacts"
W=/root/cw-a4enc; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
K=6000; SCAN_DEPTH=9; ORACLE_DEPTH=12
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_into(){ python3 - "$@" <<'PY'
import struct,glob,sys
out=sys.argv[1]; body=b""; tot=0
for p in sys.argv[2:]:
    for f in sorted(glob.glob(p)):
        try: b=open(f,'rb').read()
        except: continue
        if len(b)<8 or b[:4]!=b'JNNW': continue
        n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}

# ---- Scan pret ----
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/scanclone.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null || true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 3; }

say "=== A4 encoding-rankloss — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { say "ABORT corpus"; exit 4; }
say "  Scan=$SCAN_BIN ; K=$K ; scan d$SCAN_DEPTH ; oracle self-search d$ORACLE_DEPTH"

# ---- echantillon stratifie par phase, ecrit sub.jnnw + fens.txt + meta.tsv(pieces,selfplay_score,wdl) ----
python3 - "$W/corpus.jnnw" "$W/sub.jnnw" "$W/fens.txt" "$W/meta.tsv" "$K" <<'PY' 2>&1 | tee -a "$VERD"
import sys,struct,collections
inp,subp,fenp,metap,K=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5])
REC=38; d=open(inp,'rb').read(); assert d[:4]==b'JNNW'; body=d[8:]; tot=len(body)//REC
def pc(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
def fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
bands={0:(0,12),1:(13,20),2:(21,28),3:(29,40)}; byb=collections.defaultdict(list); per=K//4
step=max(1,tot//(K*6))
for i in range(0,tot,step):
    r=body[i*REC:(i+1)*REC]; p=pc(r)
    for bi,(lo,hi) in bands.items():
        if lo<=p<=hi and len(byb[bi])<per: byb[bi].append(r); break
recs=[]
for bi in range(4): recs+=byb[bi]
with open(subp,'wb') as f:
    f.write(b'JNNW'+struct.pack('<I',len(recs))); [f.write(r) for r in recs]
with open(fenp,'w') as ff, open(metap,'w') as mf:
    for r in recs:
        wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
        sc=struct.unpack('<i',r[33:37])[0]; wdl=struct.unpack('<b',r[37:38])[0]; p=pc(r)
        # materiel STM-POV (men=1, king=3)
        wmat=bin(wm).count('1')+3*bin(wk).count('1'); bmat=bin(bm).count('1')+3*bin(bk).count('1')
        mat=(wmat-bmat) if stm==0 else (bmat-wmat)
        ff.write(fen(wm,wk,bm,bk,stm)+"\n"); mf.write(f"{p}\t{sc}\t{wdl}\t{mat}\n")
print(f"  echantillon : {len(recs)} pos ({[len(byb[b]) for b in range(4)]} par bande)")
PY
NPOS=$(wc -l < "$W/fens.txt"); say "  positions : $NPOS"

# ---- ORACLE : deep self-search d12 (STM-POV, fiable), shardé ----
say "=== oracle self-search d$ORACLE_DEPTH (gen1) ==="
python3 - "$W/sub.jnnw" "$W/osh" "$NCPU" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; body=b[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    lo=s*per; hi=min((s+1)*per,n); m=max(0,hi-lo)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',m)+(body[lo*REC:hi*REC] if m else b''))
PY
for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/osh.$s.jnnw" "$W/odeep.$s.jnnw" "$ORACLE_DEPTH" \
    --nnue "$W/gen1.pjtw" --draw-band 0 >"$W/orl_$s.log" 2>&1 & done; wait
merge_into "$W/oracle.jnnw" "$W/odeep.*.jnnw" >/dev/null
say "  oracle : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/oracle.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) pos"

# ---- Scan static d9 (STM-POV revendiqué — POV verifie a l'analyse) ----
say "=== Scan static d$SCAN_DEPTH (book off) ==="
python3 tools/relabel_with_scan.py --in "$W/sub.jnnw" --out "$W/scan.jnnw" \
    --scan "$SCAN_BIN" --depth "$SCAN_DEPTH" --timeout 25 --progress-every 1000 >"$W/scan.log" 2>&1 \
    || { say "ABORT relabel scan"; tail -8 "$W/scan.log"|sed 's/^/  /'; exit 7; }
tail -2 "$W/scan.log"|sed 's/^/  scan> /'|tee -a "$VERD"

# ---- jass static-eval (gen1) shardé ----
say "=== jass static-eval (gen1) ==="
split -n l/$NCPU --numeric-suffixes=0 -a2 "$W/fens.txt" "$W/fensh."
for f in "$W"/fensh.*; do sh="${f##*.}"; ( : >"$W/je_$sh.txt"; while IFS= read -r fen; do [ -z "$fen" ]&&continue
    v=$("$J" --eval-position "$W/gen1.pjtw" "$fen" 2>/dev/null | head -1); echo "$v" >>"$W/je_$sh.txt"; done <"$f" ) & done; wait
cat $(ls -v "$W"/je_*.txt) > "$W/jass_eval.txt"
say "  jass evals : $(wc -l < "$W/jass_eval.txt") / $NPOS"

# ---- ANALYSE : POV-debug + rank comparison par phase (join Scan/oracle par BITBOARDS, robuste aux skips/reorder) ----
say ""; say "=== POV-DEBUG + RANG (Spearman) jass/scan vs oracle-d${ORACLE_DEPTH} vs outcome, par phase ==="
python3 - "$W/sub.jnnw" "$W/scan.jnnw" "$W/oracle.jnnw" "$W/jass_eval.txt" "$W/meta.tsv" "$ORACLE_DEPTH" <<'PY' 2>&1 | tee -a "$VERD"
import sys,struct,math
subf,scanf,oraf,jassf,metaf,od=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5],sys.argv[6]
REC=38
def load(path):
    d=open(path,'rb').read(); n=struct.unpack('<I',d[4:8])[0]; b=d[8:]; return n,b
# sub = ordre de reference (== meta == fens == jass_eval)
ns,sb=load(subf)
def key(b,i): return b[i*REC:i*REC+33]           # 32 bbs + stm = identite de position
def scoreat(b,i): return struct.unpack('<i',b[i*REC+33:i*REC+37])[0]
# dicts par identite (robuste : relabel_with_scan SKIP des positions -> index desaligne ; deep-relabel peut reordonner)
nsc,scb=load(scanf); scan_by={ key(scb,i):scoreat(scb,i) for i in range(nsc) }
nor,orb=load(oraf);  ora_by ={ key(orb,i):scoreat(orb,i) for i in range(nor) }
je=[l.strip() for l in open(jassf) if l.strip()!=""]
meta=[l.split('\t') for l in open(metaf) if l.strip()]
def f2(x):
    try:return float(x)
    except:return None
m=min(ns,len(je),len(meta))
rows=[]; miss_scan=0; miss_ora=0
for i in range(m):
    j=f2(je[i])
    if j is None: continue
    k=key(sb,i)
    if k not in scan_by: miss_scan+=1; continue
    if k not in ora_by:  miss_ora+=1;  continue
    p=int(meta[i][0]); wdl=int(meta[i][2]); mat=int(meta[i][3])
    rows.append({'j':j,'s':float(scan_by[k]),'o':float(ora_by[k]),'p':p,'wdl':float(wdl),'mat':float(mat)})
print(f"  join par bitboards : {len(rows)} apparies ; scan absents={miss_scan} oracle absents={miss_ora}")
def pearson(xs,ys):
    k=len(xs)
    if k<3:return float('nan')
    mx=sum(xs)/k;my=sum(ys)/k
    sx=math.sqrt(sum((x-mx)**2 for x in xs));sy=math.sqrt(sum((y-my)**2 for y in ys))
    if sx==0 or sy==0:return float('nan')
    return sum((xs[i]-mx)*(ys[i]-my) for i in range(k))/(sx*sy)
def rank(v):
    order=sorted(range(len(v)),key=lambda i:v[i]); r=[0.0]*len(v)
    i=0
    while i<len(order):
        j=i
        while j+1<len(order) and v[order[j+1]]==v[order[i]]: j+=1
        avg=(i+j)/2.0
        for k in range(i,j+1): r[order[k]]=avg
        i=j+1
    return r
def spear(xs,ys): return pearson(rank(xs),rank(ys))

allj=[r['j'] for r in rows]; alls=[r['s'] for r in rows]; allo=[r['o'] for r in rows]
allw=[r['wdl'] for r in rows]; allm=[r['mat'] for r in rows]
print(f"  N apparie={len(rows)} ; scan zeros={sum(1 for x in alls if x==0)} ({sum(1 for x in alls if x==0)/len(rows):.0%})")
# --- POV debug : Scan dans les 2 signes, vs materiel & outcome (verite POV) ---
print("")
print("  [POV-DEBUG] correlation SCAN (Pearson) selon la convention de signe :")
for sign,lab in ((1,'scan tel-quel'),(-1,'scan signe-inverse')):
    ss=[sign*x for x in alls]
    print(f"    {lab:20s} : vs_materiel r={pearson(ss,allm):+.3f}  vs_outcome r={pearson(ss,allw):+.3f}  vs_oracle r={pearson(ss,allo):+.3f}")
# choisir la convention qui maximise l'accord avec materiel+outcome (verite POV-robuste)
def povscore(sign): ss=[sign*x for x in alls]; return abs(pearson(ss,allm))+abs(pearson(ss,allw))
SGN = 1 if povscore(1)>=povscore(-1) else -1
alls=[SGN*x for x in alls]; [r.__setitem__('s',SGN*r['s']) for r in rows]
print(f"  => convention Scan retenue : signe x{SGN} (max accord materiel+outcome)")
# sanity jass (doit deja etre STM-POV, forte correl positive au materiel/outcome)
print(f"  [SANITY jass] vs_materiel r={pearson(allj,allm):+.3f}  vs_outcome r={pearson(allj,allw):+.3f}")

def block(tag,rws):
    j=[r['j'] for r in rws]; s=[r['s'] for r in rws]; o=[r['o'] for r in rws]; w=[r['wdl'] for r in rws]
    jo=spear(j,o); so=spear(s,o); jw=spear(j,w); sw=spear(s,w); js=spear(j,s)
    gap=so-jo
    print(f"  {tag:16s} n={len(rws):5d} | rho_jass-oracle={jo:+.3f} rho_scan-oracle={so:+.3f} (gap Scan-jass={gap:+.3f}) | rho_jass-out={jw:+.3f} rho_scan-out={sw:+.3f} | rho_jass-scan={js:+.3f}")
    return jo,so,jw,sw
print("")
print("  [RANG Spearman] plus haut = mieux ordonne. gap Scan-jass>0 sur oracle => Scan ordonne mieux => FIT-gap :")
block("GLOBAL",rows)
bands=[(0,12,'finale<=12'),(13,20,'milieu13-20'),(21,28,'milieu21-28'),(29,40,'ouverture>=29')]
res={}
for lo,hi,lab in bands:
    grp=[r for r in rows if lo<=r['p']<=hi]
    if grp: res[lab]=block(lab,grp)
# --- ROUTAGE automatique (globaux recalcules proprement) ---
gJO=spear([r['j'] for r in rows],[r['o'] for r in rows])
gSO=spear([r['s'] for r in rows],[r['o'] for r in rows])
gJW=spear([r['j'] for r in rows],[r['wdl'] for r in rows])
gSW=spear([r['s'] for r in rows],[r['wdl'] for r in rows])
print("")
print("  ===== ROUTAGE =====")
if abs(gSW)<0.05 and abs(gSO)<0.05:
    print("  Scan reste ~0-correle meme apres POV-fix => extraction Scan TOUJOURS degeneree (d9 renvoie 0 / parse KO).")
    print("  => oracle Scan inutilisable ; se reposer sur rho_jass-oracle (capacite static vs profondeur).")
else:
    gap=gSO-gJO
    if gap>0.05:
        print(f"  Scan ordonne l'oracle MIEUX que jass (gap global {gap:+.3f}) ET geometrie 8cf(Scan)⊂32cf(jass) =>")
        print(f"  notre classe PEUT representer Scan => le retard est le FIT (optimisation/target/iteration E3), PAS la capacite.")
        print(f"  => localiser la phase au gap max et prioriser E3 / meilleur objectif de fit la-bas.")
    elif gap<-0.05:
        print(f"  jass ordonne l'oracle mieux que Scan (gap {gap:+.3f}) => notre EVAL n'est pas le retard => gap = SEARCH (EBF).")
    else:
        print(f"  parite eval jass~Scan sur l'oracle (gap {gap:+.3f}) => le retard n'est PAS l'eval statique => gap = SEARCH (valide pivot EBF).")
print("  (0576 avait r=0.04/scan-out=0.03 => si POV-fix ressuscite scan-out, le verdict 'CAPACITE' de 0576 etait un artefact POV.)")
PY

commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0591 A4 encoding-rankloss : POV-debug Scan + rang Spearman jass/scan vs oracle-d12 par phase (fit vs capacite)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit verdict echoue"
say "=== fin A4 ==="
