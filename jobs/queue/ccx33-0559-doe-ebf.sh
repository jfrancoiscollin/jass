#!/usr/bin/env bash
# id: ccx33-0559-doe-ebf
# description: PHASE EBF (JFC) — DOE factoriel 2^(5-1) Res V pour REDUIRE l'EBF (~1.8 -> ~1.25 vs Scan = la fuite qui
# compose le plus en profondeur). Recherche DEGELEE (F1 baké => NMP re-activable SANS le trou de soundness). 5 leviers
# economiseurs de noeuds : A=NMP (eg_no_nmp 1off/0on) B=lmr_asym(nonpv 4/2) C=probcut(0/5) D=multicut(6/4) E=rfp(5/7).
# +1 = pruning PLUS agressif. Reponse DETERMINISTE (--search-profile prof. fixe D13) : PAYOFF = MINIMISER log(nodes)
# (moins de noeuds/prof = plus profond a temps fixe = Elo), GUARDE = detection combos (ne pas rater les shots). Analyse
# apparie ~900 combos, mains + 10 interactions 2FI, coin = min-nodes sous guarde-detection. Eval = gen1 (champion).
# Le coin sera confirme en Elo TEMPS FIXE (la reduction doit se payer en FORCE). AUCUN NNUE. expected_duration: ~30-50min.
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
ART="/root/jass/jobs/results/ccx33-0559-doe-ebf/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-ebf; rm -rf "$W"; mkdir -p "$W"
EGDBMIX=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
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
    return (f"eg_no_nmp={1 if A<0 else 0},lmr_first_full_nonpv={4 if B<0 else 2},"
            f"probcut_min_depth={0 if C<0 else 5},multicut_min_depth={6 if D<0 else 4},"
            f"rfp_max_depth={5 if E<0 else 7}")
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
names=['nmp','lmr_asym','probcut','multicut','rfp']
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
print(f"  BASELINE (defauts, run {base}) : detection={bS:.3f}  nodes~{bN:,.0f}  (M={M} positions)")
print(f"  Niveaux +1 = pruning PLUS agressif (NMP ON, lmr_asym, probcut ON, multicut bas, rfp profond).")
print(f"  PAYOFF EBF = REDUIRE log(nodes) (moins de noeuds/prof = plus profond a temps fixe). GUARDE = detection (ne pas perdre les combos).")
print(f"  Bonferroni 15 tests : |t|>2.94 ; * = |t|>1.96.")
print()
print(f"  --- classe par PAYOFF (|t_noeuds|) ---")
print(f"  {'terme':22s} {'eff logN':>9s} {'t_N':>7s}   {'d_detect':>9s} {'t_det':>7s}")
for L,nm,en,sen,tn,ds,dss,td in sorted(rows,key=lambda r:abs(r[4]),reverse=True):
    ps='***' if abs(tn)>2.94 else ('*' if abs(tn)>1.96 else '')
    dstar='!!' if td<-2.94 else ''   # detection significativement REDUITE = danger (guarde)
    kind='MAIN' if L==1 else '2FI '
    print(f"  [{kind}] {nm:22s} {en:+.4f} {tn:+7.1f}{ps:>3}   {ds:+.4f} {td:+7.1f}{dstar:>2}")
# coin optimal EBF : MINIMISER les noeuds predits SOUS CONTRAINTE detection non degradee signif.
print()
print("  === coin optimal EBF (min nodes SOUS GUARDE detection ; modele mains + 2FI signif.) ===")
gmS=sum(sum(S[i])/M for i in runs)/len(runs); gmN=sum(sum(N[i])/M for i in runs)/len(runs)
cN=[]; cS=[]
for idx in terms:
    sign={i:(lvl[i][idx[0]] if len(idx)==1 else lvl[i][idx[0]]*lvl[i][idx[1]]) for i in runs}
    en,sen=eff(N,sign); ds,dss=eff(S,sign); tn=en/sen if sen else 0; td=ds/dss if dss else 0
    if abs(tn)>2.94: cN.append((idx,en/2.0))
    if abs(td)>2.94: cS.append((idx,ds/2.0))
import itertools
def predN(x):
    v=gmN
    for idx,c in cN:
        p=1
        for k in idx: p*=x[k]
        v+=c*p
    return v
def predS(x):
    v=gmS
    for idx,c in cS:
        p=1
        for k in idx: p*=x[k]
        v+=c*p
    return v
GUARD=0.010   # tolere au plus -1 pt de detection vs baseline
best=None;bv=None
for combo in itertools.product((-1,1),repeat=5):
    x={k:combo[k] for k in range(5)}
    if predS(x) < bS-GUARD: continue      # guarde detection
    pn=predN(x)
    if bv is None or pn<bv: bv=pn; best=x; bp=(predS(x),pn)
if best is None: best={k:-1 for k in range(5)}; bp=(bS,gmN)
pnames={'nmp':'eg_no_nmp','lmr_asym':'lmr_first_full_nonpv','probcut':'probcut_min_depth','multicut':'multicut_min_depth','rfp':'rfp_max_depth'}
plusval={0:0,1:2,2:5,3:4,4:7}; minusval={0:1,1:4,2:0,3:6,4:5}
spec=",".join(pnames[names[k]]+f"={plusval[k] if best[k]==1 else minusval[k]}" for k in range(5))
active=[names[k] for k in range(5) if best[k]==1]
red=math.exp(bp[1]-gmN)  # ratio noeuds coin vs grand-mean (indicatif)
print(f"  leviers ACTIVES : {active or 'aucun (=defauts)'}")
print(f"  reduction noeuds predite au coin (vs grand-mean) ~ x{red:.3f} ; detection predite {bp[0]:.3f} (baseline {bS:.3f})")
print(f"  SPEC coin EBF : {spec}")
print(f"  => job suivant : CONFIRMER ce coin en Elo TEMPS FIXE (movetime) vs defauts — la reduction EBF doit se")
print(f"     payer en FORCE (plus profond a temps fixe), pas juste en noeuds. + verif node-EBF exact du coin.")
PY
say "=== fin DOE Res V ==="
