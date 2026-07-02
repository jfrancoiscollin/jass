#!/usr/bin/env bash
# id: ccx33-0544-doe-ext-family
# description: 2e DOE FACTORIEL (parallele au 0543 sur cpx62) — famille EXTENSIONS/REDUCTIONS que 0543 ne couvre pas.
# 2^(5-1) Res V, 16 runs, generateur I=-ABCDE (coin baseline inclus). Facteurs : A=ext_forcing(off/on cap6)
# B=ext_single_reply(off/on) C=lmr_asym nonpv(4/2, style Scan) D=iid_min_depth(0/6) E=probcut_min_depth(0/5).
# Ces leviers APPROFONDISSENT les lignes forcantes/combo (extensions) ou vont plus profond (lmr asym/iid) => famille
# la plus prometteuse pour le PAYOFF detection. Reponse DETERMINISTE via --search-profile profondeur fixe D=13 :
# detection combo (PAYOFF) + log(nodes) exact (COUT). Analyse apparie position-par-position sur ~900 combos ;
# effets principaux + 10 interactions 2-facteurs ; coin optimal = recherche sur 32 coins (mains + 2FI signif.).
# AUCUN NNUE. AUCUN OFAT. expected_duration: ~20-30 min (ccx33 8 coeurs).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0544-doe-ext-family/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-doe2; rm -rf "$W"; mkdir -p "$W"
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
COMBOS=jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen
DEPTH=13; NSAMP=900

say "=== build jass depuis main (qs_sacs baké ON) + JASS_TIME_BREAKDOWN (search-profile) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON -DJASS_TIME_BREAKDOWN=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$EGDBMIX" | gunzip > "$W/champ.pjtw" || { say "ABORT champ egdbmix absent"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"

# ---- design 2^(5-1) Res V + sous-echantillon stratifie par tempi (famille extensions) ----
python3 - "$W" "$COMBOS" "$NSAMP" <<'PY'
import sys,re
W,COMBOS,NSAMP=sys.argv[1],sys.argv[2],int(sys.argv[3])
runs=[]
for A in(-1,1):
 for B in(-1,1):
  for C in(-1,1):
   for D in(-1,1):
    E=-A*B*C*D
    runs.append((A,B,C,D,E))
def frag(k,plus):
    fp={0:"ext_forcing=1,forcing_ext_cap=6",1:"ext_single_reply=1",2:"lmr_first_full_nonpv=2",3:"iid_min_depth=6",4:"probcut_min_depth=5"}
    fm={0:"ext_forcing=0,forcing_ext_cap=0",1:"ext_single_reply=0",2:"lmr_first_full_nonpv=4",3:"iid_min_depth=0",4:"probcut_min_depth=0"}
    return fp[k] if plus else fm[k]
def spec(l):
    return ",".join(frag(k, l[k]>0) for k in range(5))
with open(f"{W}/design.tsv","w") as o:
    for i,l in enumerate(runs):
        o.write(f"{i}\t{l[0]}\t{l[1]}\t{l[2]}\t{l[3]}\t{l[4]}\t{spec(l)}\n")
bins={}
for line in open(COMBOS):
    s=line.strip()
    if not s or s.startswith('#'): continue
    m=re.search(r'tempi=(\d+)',line); t=int(m.group(1)) if m else 0
    bins.setdefault(t,[]).append(line.rstrip('\n'))
per=max(1,NSAMP//max(1,len(bins))); samp=[]
for t in sorted(bins):
    lst=bins[t]; stride=max(1,len(lst)//per); samp+=lst[::stride][:per]
open(f"{W}/sample.fen","w").write("\n".join(samp)+"\n")
print(f"design=16 runs ; sample={len(samp)} combos ; bins={sorted(bins)}")
PY
NS=$(grep -vcE '^#|^\s*$' "$W/sample.fen"); say "  echantillon : $NS combos, profondeur fixe D=$DEPTH (deterministe)"

cat > "$W/worker.py" <<'PY'
import sys,re,subprocess
J,CHAMP,SAMPLE,SPEC,DEPTH,OUT=sys.argv[1:7]; DEPTH=int(DEPTH)
def parse_win(c):
    m=re.search(r'win=(\S+)',c)
    if not m: return None
    p=re.split(r'[-x]',m.group(1))
    try: return (int(p[0]),int(p[1]))
    except: return None
PROF=re.compile(r'nodes=(\d+)\s+bestmove=(\d+)-(\d+)-\d+')
out=open(OUT,'w')
for line in open(SAMPLE):
    line=line.rstrip('\n')
    if not line.strip() or line.startswith('#'): continue
    fen,comment=(line.split('#',1)+[''])[:2]; fen=fen.strip(); win=parse_win(comment)
    try:
        r=subprocess.run([J,'--search-profile',fen,str(DEPTH),'0',CHAMP,SPEC],capture_output=True,text=True,timeout=120)
        mm=PROF.search(r.stdout)
    except Exception: mm=None
    if not mm: out.write("0 0\n"); continue
    out.write(f"{int(mm.group(1))} {1 if (win and int(mm.group(2))==win[0] and int(mm.group(3))==win[1]) else 0}\n")
out.close()
PY

say ""
say "=== 16 runs en parallele (profondeur fixe, deterministe) ==="
while IFS=$'\t' read -r idx a b c d e spec; do
  ( python3 "$W/worker.py" "$J" "$W/champ.pjtw" "$W/sample.fen" "$spec" "$DEPTH" "$W/solve_${idx}.txt" ; echo "DONE run $idx" ) &
done < "$W/design.tsv"
wait
say "  runs termines : $(ls "$W"/solve_*.txt 2>/dev/null | wc -l)/16"
cp "$W"/solve_*.txt "$ART/" 2>/dev/null; cp "$W/design.tsv" "$ART/"; cp "$W/sample.fen" "$ART/" 2>/dev/null

say ""
say "=== ANALYSE : estimateur apparie position-par-position (effets principaux + 10 interactions 2FI) ==="
python3 - "$W" <<'PY' 2>&1 | tee -a "$RES"
import sys,math,itertools
W=sys.argv[1]
names=['ext_forcing','single_reply','lmr_asym','iid','probcut']
design=[]
for line in open(f"{W}/design.tsv"):
    p=line.rstrip('\n').split('\t'); design.append((int(p[0]),[int(p[1]),int(p[2]),int(p[3]),int(p[4]),int(p[5])],p[6]))
lvl={i:l for i,l,_ in design}
N={};S={};M=None
for i,_,_ in design:
    rows=[ln.split() for ln in open(f"{W}/solve_{i}.txt")]
    N[i]=[math.log(max(1,int(r[0]))) for r in rows]; S[i]=[int(r[1]) for r in rows]
    M=len(rows) if M is None else min(M,len(rows))
runs=[i for i,_,_ in design]
def eff(Y,sign):
    plus=[i for i in runs if sign[i]==1]; minus=[i for i in runs if sign[i]==-1]
    ej=[(sum(Y[i][j] for i in plus)/len(plus))-(sum(Y[i][j] for i in minus)/len(minus)) for j in range(M)]
    e=sum(ej)/M; v=sum((x-e)**2 for x in ej)/(M-1); return e,math.sqrt(v/M)
terms=[(k,) for k in range(5)]+[(i,j) for i in range(5) for j in range(i+1,5)]
rows=[]
for idx in terms:
    sign={i:(lvl[i][idx[0]] if len(idx)==1 else lvl[i][idx[0]]*lvl[i][idx[1]]) for i in runs}
    en,sen=eff(N,sign); ds,dss=eff(S,sign)
    rows.append((len(idx),'*'.join(names[k] for k in idx),en,sen,en/sen if sen else 0,ds,dss,ds/dss if dss else 0))
base=[i for i,l,_ in design if l==[-1,-1,-1,-1,-1]][0]
bN=sum(math.exp(x) for x in N[base])/M; bS=sum(S[base])/M
print(f"  BASELINE (defauts bakes, run {base}) : detection={bS:.3f}  nodes~{bN:,.0f}  (M={M} positions)")
print(f"  Niveaux +1 = extensions/reductions ACTIVEES (ext_forcing, single_reply, lmr asym, iid, probcut).")
print(f"  PAYOFF = detection ; COUT = log(nodes). Bonferroni 15 tests : |t|>2.94 ; * = |t|>1.96.")
print()
print(f"  --- classe par PAYOFF (|t_detection|) ---")
print(f"  {'terme':24s} {'d_detect':>9s} {'t_det':>7s}   {'cout logN':>10s} {'t_N':>7s}")
for L,nm,en,sen,tn,ds,dss,td in sorted(rows,key=lambda r:abs(r[7]),reverse=True):
    ps='***' if abs(td)>2.94 else ('*' if abs(td)>1.96 else '')
    print(f"  [{'MAIN' if L==1 else '2FI '}] {nm:24s} {ds:+.4f} {td:+7.1f}{ps:>3}   {en:+.4f} {tn:+7.1f}")
print()
print("  === coin optimal predit (modele detection = mains + 2FI significatifs, recherche sur 32 coins) ===")
fragplus={0:"ext_forcing=1,forcing_ext_cap=6",1:"ext_single_reply=1",2:"lmr_first_full_nonpv=2",3:"iid_min_depth=6",4:"probcut_min_depth=5"}
fragminus={0:"ext_forcing=0,forcing_ext_cap=0",1:"ext_single_reply=0",2:"lmr_first_full_nonpv=4",3:"iid_min_depth=0",4:"probcut_min_depth=0"}
gmS=sum(sum(S[i])/M for i in runs)/len(runs); gmN=sum(sum(N[i])/M for i in runs)/len(runs)
coefs=[]
for idx in terms:
    sign={i:(lvl[i][idx[0]] if len(idx)==1 else lvl[i][idx[0]]*lvl[i][idx[1]]) for i in runs}
    en,sen=eff(N,sign); ds,dss=eff(S,sign); td=ds/dss if dss else 0
    if abs(td)>2.94: coefs.append((idx, ds/2.0, td, en/2.0))
def predict(x):
    ps=gmS; pn=gmN
    for idx,cS,tS,cN in coefs:
        v=1
        for k in idx: v*=x[k]
        ps+=cS*v; pn+=cN*v
    return ps,pn
# Les extensions font EXPLOSER les noeuds a profondeur fixe (=> plus superficiel a temps fixe). On internalise
# le cout : le coin retenu doit rester dans un BUDGET de noeuds (<= +0.6 log ~ 1 ply plus superficiel a EBF 1.8).
NODE_BUDGET=0.6
baseN=predict({k:-1 for k in range(5)})[1]
best_corner=None; best_val=None; best_pred=(bS,None)
for combo in itertools.product((-1,1),repeat=5):
    x={k:combo[k] for k in range(5)}
    ps,pn=predict(x)
    if (pn-baseN)>NODE_BUDGET: continue          # trop cher a temps fixe -> rejete
    key=(ps,-pn)
    if best_val is None or key>best_val: best_val=key; best_corner=x; best_pred=(ps,pn)
if best_corner is None:  # rien de faisable dans le budget -> baseline
    best_corner={k:-1 for k in range(5)}; best_pred=(bS,baseN)
if not coefs:
    print(f"  AUCUN effet/interaction ne releve la detection de facon signif. (Bonferroni) => les defauts")
    print(f"  bakes sont deja optimaux sur cette famille (extensions/reductions). Conclusion propre (hors OFAT).")
    best_corner={k:-1 for k in range(5)}; best_pred=(bS,baseN)
else:
    gainok = best_pred[0]-bS
    print(f"  contrainte cout : log-nodes du coin <= baseline +{NODE_BUDGET} (~1 ply @EBF1.8) pour rester net a temps fixe")
    print(f"  detection predite au coin optimal (dans budget) = {best_pred[0]:.3f}  (baseline {bS:.3f}, gain {gainok:+.3f})")
    print(f"  cout log-nodes predit vs baseline = {best_pred[1]-baseN:+.3f}")
    if gainok<=0.0:
        print(f"  NB : aucun coin ne bat la baseline en detection DANS le budget noeud => les extensions")
        print(f"  n'apportent rien de net a temps fixe (gain detection paye trop cher en profondeur).")
relaxed=[names[k] for k in range(5) if best_corner[k]==1]
spec=",".join(fragplus[k] if best_corner[k]==1 else fragminus[k] for k in range(5))
print(f"  leviers ACTIVES au coin optimal : {relaxed or 'aucun (=defauts)'}")
print(f"  SPEC coin optimal predit : {spec}")
print(f"  => si gain detection : confirmer ce coin (et/ou combine avec le coin de 0543) en PARTIES (~4600).")
PY
say "=== fin DOE ext-family ==="
