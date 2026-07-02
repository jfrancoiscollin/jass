#!/usr/bin/env bash
# id: cpx62-0543-doe-resv-nodes
# description: DOE FACTORIEL (remplace l'OFAT 0542). 2^(5-1) Resolution V, 16 runs, 5 facteurs de pruning post-bake
# qs_sacs : A=rfp_max_depth(5/3) B=rfp_margin(100/140) C=razor_max_depth(4/0) D=multicut_min_depth(6/8)
# E=no_reduce_forcing(0/1). Res V => TOUS les effets principaux ET toutes les 10 interactions 2-facteurs estimables
# proprement (aliasees seulement avec >=3FI, negligeable). Reponse DETERMINISTE (movetime=0, --search-profile a
# profondeur fixe D=13) : (1) log(nodes) EXACT = combien de noeuds pour atteindre la profondeur = quel reglage va le
# plus profond a temps fixe (PRIMAIRE, node-EBF-based, jamais time-based) ; (2) detection combo (bestmove==win) =
# GARDE (un reglage qui economise des noeuds mais rate un combo est rejete). Analyse : estimateur apparie
# position-par-position (SE = ecart-type inter-positions / sqrt(M)) => puissance auto-calibree sur ~900 combos
# sous-echantillonnes (le calcul de taille montre que l'effet noeud, gros+deterministe, sur-resout bien en-dessous
# de M=900). Le coin optimal predit sera confirme en parties (~4600, job suivant) pour le chiffrer en Elo. AUCUN
# NNUE. AUCUN OFAT. expected_duration: ~15-25 min.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0543-doe-resv-nodes/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-doe; rm -rf "$W"; mkdir -p "$W"
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

# ---- design 2^(5-1) Res V + sous-echantillon stratifie par tempi ----
python3 - "$W" "$COMBOS" "$NSAMP" <<'PY'
import sys,re
W,COMBOS,NSAMP=sys.argv[1],sys.argv[2],int(sys.argv[3])
# design
runs=[]
for A in(-1,1):
 for B in(-1,1):
  for C in(-1,1):
   for D in(-1,1):
    E=-A*B*C*D   # generator I=-ABCDE (Res V) : contient le coin baseline all -1
    runs.append((A,B,C,D,E))
def spec(l):
    A,B,C,D,E=l
    return (f"rfp_max_depth={5 if A<0 else 3},rfp_margin={100 if B<0 else 140},"
            f"razor_max_depth={4 if C<0 else 0},multicut_min_depth={6 if D<0 else 8},"
            f"no_reduce_forcing={0 if E<0 else 1}")
with open(f"{W}/design.tsv","w") as o:
    for i,l in enumerate(runs):
        o.write(f"{i}\t{l[0]}\t{l[1]}\t{l[2]}\t{l[3]}\t{l[4]}\t{spec(l)}\n")
# stratified subsample by tempi bin
bins={}
for line in open(COMBOS):
    s=line.strip()
    if not s or s.startswith('#'): continue
    m=re.search(r'tempi=(\d+)',line); t=int(m.group(1)) if m else 0
    bins.setdefault(t,[]).append(line.rstrip('\n'))
per=max(1,NSAMP//max(1,len(bins)))
samp=[]
for t in sorted(bins):
    lst=bins[t]
    stride=max(1,len(lst)//per)
    samp+=lst[::stride][:per]
with open(f"{W}/sample.fen","w") as o:
    for l in samp: o.write(l+"\n")
print(f"design=16 runs ; sample={len(samp)} combos across tempi bins {sorted(bins)}")
PY
say "  $(tail -1 "$W/cmakedummy" 2>/dev/null)"
NS=$(grep -vcE '^#|^\s*$' "$W/sample.fen"); say "  echantillon : $NS combos, profondeur fixe D=$DEPTH (deterministe)"

# ---- worker : un run = un config, boucle sur l'echantillon, ecrit 'nodes solve' par ligne ----
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
    fen,comment=(line.split('#',1)+[''])[:2]
    fen=fen.strip(); win=parse_win(comment)
    try:
        r=subprocess.run([J,'--search-profile',fen,str(DEPTH),'0',CHAMP,SPEC],
                         capture_output=True,text=True,timeout=120)
        mm=PROF.search(r.stdout)
    except Exception:
        mm=None
    if not mm: out.write("0 0\n"); continue
    nodes=int(mm.group(1)); bf=int(mm.group(2)); bt=int(mm.group(3))
    solve=1 if (win and bf==win[0] and bt==win[1]) else 0
    out.write(f"{nodes} {solve}\n")
out.close()
PY

say ""
say "=== 16 runs en parallele (1 config/coeur, profondeur fixe, deterministe) ==="
while IFS=$'\t' read -r idx a b c d e spec; do
  ( python3 "$W/worker.py" "$J" "$W/champ.pjtw" "$W/sample.fen" "$spec" "$DEPTH" "$W/solve_${idx}.txt" ; echo "DONE run $idx" ) &
done < "$W/design.tsv"
wait
say "  runs termines : $(ls "$W"/solve_*.txt 2>/dev/null | wc -l)/16"
cp "$W"/solve_*.txt "$ART/" 2>/dev/null; cp "$W/design.tsv" "$ART/"; cp "$W/sample.fen" "$ART/" 2>/dev/null

say ""
say "=== ANALYSE : estimateur apparie position-par-position (effets principaux + 10 interactions 2FI) ==="
python3 - "$W" <<'PY' 2>&1 | tee -a "$RES"
import sys,math
W=sys.argv[1]
names=['rfp_depth','rfp_margin','razor','multicut','noreduce']
design=[]
for line in open(f"{W}/design.tsv"):
    p=line.rstrip('\n').split('\t'); design.append((int(p[0]),[int(p[1]),int(p[2]),int(p[3]),int(p[4]),int(p[5])],p[6]))
lvl={i:l for i,l,_ in design}
N={};S={}
M=None
for i,_,_ in design:
    rows=[ln.split() for ln in open(f"{W}/solve_{i}.txt")]
    N[i]=[math.log(max(1,int(r[0]))) for r in rows]
    S[i]=[int(r[1]) for r in rows]
    M=len(rows) if M is None else min(M,len(rows))
runs=[i for i,_,_ in design]
def eff(Y,sign):
    plus=[i for i in runs if sign[i]==1]; minus=[i for i in runs if sign[i]==-1]
    ej=[ (sum(Y[i][j] for i in plus)/len(plus)) - (sum(Y[i][j] for i in minus)/len(minus)) for j in range(M) ]
    e=sum(ej)/M; v=sum((x-e)**2 for x in ej)/(M-1); return e, math.sqrt(v/M)
terms=[(k,) for k in range(5)]+[(i,j) for i in range(5) for j in range(i+1,5)]
rows=[]
for idx in terms:
    sign={i: (lvl[i][idx[0]] if len(idx)==1 else lvl[i][idx[0]]*lvl[i][idx[1]]) for i in runs}
    en,sen=eff(N,sign); ds,dss=eff(S,sign)
    nm='*'.join(names[k] for k in idx)
    rows.append((len(idx),nm,en,sen,en/sen if sen else 0,ds,dss,ds/dss if dss else 0))
# baseline = run all -1 (= defauts bakes)
base=[i for i,l,_ in design if l==[-1,-1,-1,-1,-1]][0]
bN=sum(math.exp(x) for x in N[base])/M; bS=sum(S[base])/M
print(f"  BASELINE (defauts bakes, run {base}) : detection={bS:.3f}  nodes~{bN:,.0f}  (M={M} positions)")
print(f"  Les niveaux +1 = MOINS de pruning (rfp court/large, razor off, multicut profond, no-reduce).")
print(f"  PAYOFF = detection (relacher aide-t-il a trouver les combos ?) ; COUT = log(nodes).")
print(f"  Seuil signif. Bonferroni 15 tests : |t|>2.94 (alpha=0.05/15) ; * = |t|>1.96.")
print()
print(f"  --- classe par PAYOFF (|t_detection|) ---")
print(f"  {'terme':22s} {'d_detect':>9s} {'t_det':>7s}   {'cout logN':>10s} {'t_N':>7s}")
for L,nm,en,sen,tn,ds,dss,td in sorted(rows,key=lambda r:abs(r[7]),reverse=True):
    ps='***' if abs(td)>2.94 else ('*' if abs(td)>1.96 else '')
    kind='MAIN' if L==1 else '2FI '
    print(f"  [{kind}] {nm:22s} {ds:+.4f} {td:+7.1f}{ps:>3}   {en:+.4f} {tn:+7.1f}")
# coin optimal : on AJUSTE le modele (intercept + effets/interactions SIGNIFICATIFS) et on cherche le coin
# des 2^5=32 qui MAXIMISE la detection predite (interactions incluses = le point de JFC), cout-noeud en depart.
print()
print("  === coin optimal predit (modele detection = mains + 2FI significatifs, recherche sur 32 coins) ===")
pnames={'rfp_depth':'rfp_max_depth','rfp_margin':'rfp_margin','razor':'razor_max_depth','multicut':'multicut_min_depth','noreduce':'no_reduce_forcing'}
plusval={0:3,1:140,2:0,3:8,4:1}; minusval={0:5,1:100,2:4,3:6,4:0}
# grand mean + coefficients (coef = effet/2, design orthogonal ; on ne garde que |t|>2.94 Bonferroni)
gmS=sum(sum(S[i])/M for i in runs)/len(runs)
gmN=sum(sum(N[i])/M for i in runs)/len(runs)
coefs=[]  # (idx_tuple, coefS, tS, coefN)
for idx in terms:
    sign={i:(lvl[i][idx[0]] if len(idx)==1 else lvl[i][idx[0]]*lvl[i][idx[1]]) for i in runs}
    en,sen=eff(N,sign); ds,dss=eff(S,sign); td=ds/dss if dss else 0
    if abs(td)>2.94:  # significatif (payoff)
        coefs.append((idx, ds/2.0, td, en/2.0))
def predict(x):  # x = dict k->(+1/-1)
    ps=gmS; pn=gmN
    for idx,cS,tS,cN in coefs:
        v=1
        for k in idx: v*=x[k]
        ps+=cS*v; pn+=cN*v
    return ps,pn
import itertools
best_corner=None; best_val=None
for combo in itertools.product((-1,1),repeat=5):
    x={k:combo[k] for k in range(5)}
    ps,pn=predict(x)
    key=(ps,-pn)  # max detection, tie-break min nodes
    if best_val is None or key>best_val: best_val=key; best_corner=x; best_pred=(ps,pn)
if not coefs:
    print(f"  AUCUN effet/interaction ne releve la detection de facon signif. (Bonferroni) => les defauts")
    print(f"  bakes sont deja optimaux sur ces 5 leviers. Conclusion (que l'OFAT ne donnait pas proprement) :")
    print(f"  le gain combo est deja capte par qs_sacs ; le pruning n'est pas le levier. Chercher ailleurs.")
    best_corner={k:-1 for k in range(5)}; best_pred=(bS,None)
else:
    print(f"  effets/interactions retenus (|t_det|>2.94) : "+", ".join('*'.join(names[k] for k in idx) for idx,_,_,_ in coefs))
    print(f"  detection predite au coin optimal = {best_pred[0]:.3f}  (baseline {bS:.3f}, gain {best_pred[0]-bS:+.3f})")
    print(f"  cout log-nodes predit vs baseline = {best_pred[1]-gmN:+.3f} (autour du grand-mean)")
relaxed=[names[k] for k in range(5) if best_corner[k]==1]
best={names[k]:(plusval[k] if best_corner[k]==1 else minusval[k]) for k in range(5)}
spec=",".join(pnames[n]+f"={best[n]}" for n in names)
print(f"  leviers RELACHES au coin optimal : {relaxed or 'aucun (=defauts)'}")
print(f"  SPEC coin optimal predit : {spec}")
print(f"  => job suivant : CONFIRMER ce coin vs baseline bake en PARTIES (~4600 pour >=20 Elo @80%).")
PY
say "=== fin DOE Res V ==="
