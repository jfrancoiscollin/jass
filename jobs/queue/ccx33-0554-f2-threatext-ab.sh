#!/usr/bin/env bash
# id: ccx33-0554-f2-threatext-ab
# description: F2 (audit) — A/B de qs_threat_ext (moitie MANQUANTE de la quiescence de Scan : refuse le stand-pat en
# feuille calme-SOUS-MENACE, resout par 1-ply). Deja porte+gate off (byte-identical). Complete l architecture recherche
# (JFC : la tester avant de conclure sur la chaine eval). Protocole standard : (1) DETECTION combos par-position +
# node-EBF EXACT (search-profile prof. fixe D13, qs_threat_ext=1 vs off, apparie ~900 combos) ; (2) Elo TEMPS FIXE
# (jass_vs_jass movetime, dilf, shards capes 16gb). Gate : detection >= ET Elo >= ET surcout noeuds raisonnable => baker.
# Build depuis main (F1 deja bake => confirme aussi que F1 compile). AUCUN NNUE. ~30-50min.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0554-f2-threatext-ab/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-f2; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
COMBOS=jobs/results/cpx62-0534-combo-gen-balanced/artefacts/combos_balanced.fen
DILF=data/dilf_combinations.fen
DEPTH=13; NSAMP=900; MT=0.3; JUDGE_SHARDS=4

say "=== build jass depuis main (F1 bake + JASS_TIME_BREAKDOWN) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON -DJASS_TIME_BREAKDOWN=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL (F1 casse-t-il la compil ?!)"; tail -15 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  (build OK => F1 compile bien sur main)"

# ---- (1) DETECTION + node-EBF apparie (qs_threat_ext=1 vs off), profondeur fixe, deterministe ----
say ""; say "=== (1) DETECTION combos + node-EBF EXACT (D$DEPTH, qs_threat_ext on vs off, ~$NSAMP combos) ==="
python3 - "$W" "$COMBOS" "$NSAMP" <<'PY'
import sys,re,random
W,COMBOS,NSAMP=sys.argv[1],sys.argv[2],int(sys.argv[3])
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
print(f"  echantillon={len(samp)}")
PY
cat > "$W/worker.py" <<'PY'
import sys,re,subprocess
J,CHAMP,SAMPLE,SPEC,DEPTH,OUT=sys.argv[1:7]; DEPTH=int(DEPTH)
def pw(c):
    m=re.search(r'win=(\S+)',c);
    if not m: return None
    p=re.split(r'[-x]',m.group(1))
    try: return (int(p[0]),int(p[1]))
    except: return None
PROF=re.compile(r'nodes=(\d+)\s+bestmove=(\d+)-(\d+)-\d+'); out=open(OUT,'w')
for line in open(SAMPLE):
    line=line.rstrip('\n')
    if not line.strip() or line.startswith('#'): continue
    fen,c=(line.split('#',1)+[''])[:2]; fen=fen.strip(); win=pw(c)
    try: r=subprocess.run([J,'--search-profile',fen,str(DEPTH),'0',CHAMP,SPEC],capture_output=True,text=True,timeout=120); mm=PROF.search(r.stdout)
    except: mm=None
    if not mm: out.write("0 0\n"); continue
    out.write(f"{int(mm.group(1))} {1 if (win and int(mm.group(2))==win[0] and int(mm.group(3))==win[1]) else 0}\n")
out.close()
PY
shard_run(){ local tag="$1" spec="$2"
  for s in $(seq 0 $((NCPU-1))); do
    awk -v n="$NCPU" -v r="$s" 'NR%n==r' "$W/sample.fen" > "$W/sh_${tag}_$(printf %02d $s).fen"
    ( python3 "$W/worker.py" "$J" "$W/gen1.pjtw" "$W/sh_${tag}_$(printf %02d $s).fen" "$spec" "$DEPTH" "$W/sh_${tag}_$(printf %02d $s).out" ) &
  done; wait; }
shard_run off ""
shard_run on "qs_threat_ext=1"
python3 - "$W" <<'PY' 2>&1 | tee -a "$RES"
import glob,math,sys,statistics
W=sys.argv[1]
def load(tag):
    N=[];S=[]
    for f in sorted(glob.glob(f"{W}/sh_{tag}_*.out")):
        for ln in open(f):
            a,b=ln.split(); N.append(int(a)); S.append(int(b))
    return N,S
No,So=load("off"); Nn,Sn=load("on"); m=min(len(No),len(Nn))
if m==0: print("  (aucune position)"); raise SystemExit
det_off=sum(So[:m])/m; det_on=sum(Sn[:m])/m
import statistics
ln_off=statistics.mean(math.log(max(1,x)) for x in No[:m]); ln_on=statistics.mean(math.log(max(1,x)) for x in Nn[:m])
ratio=math.exp(ln_on-ln_off)
print(f"  M={m}  detection off={det_off:.3f} on={det_on:.3f}  (delta {det_on-det_off:+.3f})")
print(f"  node-EBF (log-nodes) : ratio on/off = {ratio:.3f} (surcout noeuds)")
PY

# ---- (2) Elo temps fixe (qs_threat_ext=1 vs off) ----
say ""; say "=== (2) Elo TEMPS FIXE movetime ${MT}s (qs_threat_ext=1 vs off), dilf ==="
for s in $(seq 0 $((JUDGE_SHARDS-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen1.pjtw" \
    --jass-b "$J" --pattern-b "$W/gen1.pjtw" --movetime "$MT" --pairs 1 --max-plies 180 --shard "$s" --nshards "$JUDGE_SHARDS" \
    --quiet --openings-file "$DILF" --search-params-a "qs_threat_ext=1" --search-params-b "" >"$W/e.$s" 2>&1 & done
wait
python3 - "$W" "$JUDGE_SHARDS" <<'PY' 2>&1 | tee -a "$RES"
import sys,math; W=sys.argv[1]; ns=int(sys.argv[2]); a=d=b=0
for s in range(ns):
    try:
        last=[l for l in open(f"{W}/e.{s}") if l.startswith("RESULT")][-1]
        _,x,y,z=last.split(); a+=int(x);d+=int(y);b+=int(z)
    except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"  Elo threat_ext ON vs OFF : games={g} rate={r:.4f}+-{1.96*se:.4f} elo~{elo:+.0f}")
print(f"  GATE : detection>= ET Elo borne basse>0.50 ET surcout noeuds raisonnable => BAKER qs_threat_ext.")
PY
say "=== fin F2 A/B ==="
