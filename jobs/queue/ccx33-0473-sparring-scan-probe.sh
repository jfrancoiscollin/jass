#!/usr/bin/env bash
# id: ccx33-0473-sparring-scan-probe
# description: LEVIER B EN PROBE (demande JFC : "voir ce que ca donne" pendant que cpx finit 0465). SPARRING vs Scan : jass
# (egdbmix) joue CONTRE Scan, chaque position etiquetee par le RESULTAT REEL de la partie (W/D/L, POV du trait) — AUCUNE eval
# moteur dans le label => NI distillation (!= eval-Scan cible) NI auto-supervision (!= labels-jass, mort 0460-0468). Un
# adversaire qui voit ~95% des shots PUNIT les coups shot-vulnerables de jass => les positions ou jass marche dans un shot sont
# enfin etiquetees PERDANTES => l'eval lineaire apprend la securite tactique (sans le plafond des 52% du self-relabel). Probe :
# ~1500 ouvertures milieu diverses (echantillon du pool) x2 couleurs vs Scan, d11 no-DB, dump fens+outcome -> flux sparring
# (REEQUILIBRE W/D/L, cf biais-perte) -> fit pool+egdb+sparring -> juge 0440 + IC95 vs egdbmix (0.302). Dependance-Scan =
# ALLUMAGE transitoire (derriere : self-play depuis le champion-B). Si 0440 monte (>0.35, voire vers ~Scan) => le levier vit.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0473-sparring-scan-probe/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-sparring; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-sparring
POOL_TRIM=12000000; NEGDB=4000000; NOPEN=1500; MID_LO=14; MID_HI=40; TARGET_FRAC=30; GENDEPTH=11
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable ($SCAN_BIN)"; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  Scan : $SCAN_BIN ; egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
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

say "=== assemble pool + echantillonne ${NOPEN} ouvertures milieu diverses -> ${NCPU} shards FEN ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
python3 - "$W/pool.jnnw" "$W/op" "$NOPEN" "$MID_LO" "$MID_HI" "$NCPU" <<'PY' | tee -a "$RES"
import struct,sys,random; REC=38
pool,pre,cap,lo,hi,nsh=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
random.seed(73); idx=list(range(n)); random.shuffle(idx); fens=[]
sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
for i in idx:
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if not (lo<=pc<=hi): continue
    f=f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}"
    fens.append(f)
    if len(fens)>=cap: break
for s in range(nsh):
    with open(f"{pre}.{s}.fen","w") as o:
        for f in fens[s::nsh]: o.write(f+"\n")
print(f"  ouvertures milieu : {len(fens)} -> {nsh} shards")
PY

say "=== SPARRING : jass(egdbmix) vs Scan depuis chaque ouverture, d${GENDEPTH} no-DB, dump fens+outcome (parallele) ==="
unset JASS_EGDB_PATH
for s in $(seq 0 $((NCPU-1))); do
  ( python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" --scan-bb-size 0 \
      --depth "$GENDEPTH" --pairs 1 --openings-file "$W/op.$s.fen" --dump-games-dir "$W/g$s" >"$W/spar$s.log" 2>&1 ) &
done; wait
NG=$(ls "$W"/g*/game-*.json 2>/dev/null | wc -l); say "  parties sparring jouees : ${NG}"
[ "${NG:-0}" -ge 200 ] || { say "ABORT: trop peu de parties ($NG) — voir spar0.log"; tail -6 "$W"/spar0.log|sed 's/^/  /'; exit 7; }

say "=== extrait positions + label = RESULTAT REEL (POV trait), puis REEQUILIBRE W/D/L ==="
python3 - "$W" "$W/spar_raw.jnnw" "$ART/SPAR_DIST.txt" <<'PY' | tee -a "$RES"
import struct,sys,glob,json,os
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards
_R=struct.Struct("<QQQQBib"); Wd=sys.argv[1]; out=sys.argv[2]; distout=sys.argv[3]
recs={1:bytearray(),0:bytearray(),-1:bytearray()}; cnt={1:0,0:0,-1:0}
for f in glob.glob(os.path.join(Wd,"g*","game-*.json")):
    try: g=json.load(open(f))
    except: continue
    outc=g.get("outcome"); fens=g.get("fens") or []
    if outc not in ("W","D","L") or not fens: continue
    white_won = (outc=="W"); draw=(outc=="D")
    for fen in fens:
        try: stm,wm,wk,bm,bk=fen_to_bitboards(fen)
        except Exception: continue
        if draw: wdl=0
        else:
            stm_white=(stm==0); wdl = 1 if (white_won==stm_white) else -1
        recs[wdl]+= _R.pack(wm,wk,bm,bk,stm,0,wdl); cnt[wdl]+=1
print(f"  positions sparring brutes : W={cnt[1]} D={cnt[0]} L={cnt[-1]} (total {sum(cnt.values())})")
# REEQUILIBRE : cap chaque classe au min*facteur pour ne pas degenerer en "tout perdant"
import random; random.seed(7); REC=38
def split(buf):
    n=len(buf)//REC; return [bytes(buf[i*REC:(i+1)*REC]) for i in range(n)]
W_=split(recs[1]); D_=split(recs[0]); L_=split(recs[-1])
base=max(1,min(len(W_),len(D_)))             # ancre sur la plus petite classe non-perte
capW=len(W_); capD=len(D_); capL=min(len(L_), 2*(capW+capD))  # L au plus 2x (W+D) : garde le signal-perte sans noyer
random.shuffle(L_); L_=L_[:capL]
bal=W_+D_+L_; random.shuffle(bal)
open(out,'wb').write(b'JNNW'+struct.pack('<I',len(bal))+b''.join(bal))
open(distout,'w').write(f"raw W={cnt[1]} D={cnt[0]} L={cnt[-1]} ; rebalanced W={capW} D={capD} L={capL} total={len(bal)}\n")
print(f"  reequilibre : W={capW} D={capD} L={capL} (total {len(bal)})")
PY
NS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/spar_raw.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${NS:-0}" -ge 20000 ] || { say "ABORT: flux sparring trop maigre ($NS)"; exit 7; }
cp "$W/spar_raw.jnnw" "$ART/sparring.jnnw" 2>/dev/null || true

say "=== fit : pool + egdb + flux SPARRING sur-pondere (~${TARGET_FRAC}%) ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8013 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
REP=$(python3 -c "p=$POOL_TRIM+$NEGDB; f=$TARGET_FRAC/100.0; import math; print(max(1,math.ceil(f/(1-f)*p/$NS)))")
python3 - "$W/spar_raw.jnnw" "$W/spar_heavy.jnnw" "$REP" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',n*int(sys.argv[3]))+body*int(sys.argv[3]))
PY
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/spar_heavy.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])")
NSH=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/spar_heavy.jnnw','rb').read(8)[4:8])[0])")
say "  corpus : ${NMIX}  (sparring ${NSH} = $((100*NSH/NMIX))% ; uniques=${NS}, replique x${REP})"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_spar.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -6 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_spar.pjtw" > "$ART/champion-sparring.pjtw.gz"; rm -f "$W/feat"

conv_ci(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=[]
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw.append(0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0))
n=len(aw)
if not n: print("NA NA NA 0"); sys.exit(0)
m=sum(aw)/n; seed=12345; boots=[]
for _ in range(2000):
    acc=0
    for _ in range(n):
        seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
    boots.append(acc/n)
boots.sort(); print(f"{m:.3f} {boots[50]:.3f} {boots[1949]:.3f} {n}")
PY
}
say ""; say "=== GATE 0440 : sparring vs Scan (DILF complet, d${D}) + IC95 ==="
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_spar.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-spar" >"$W/cs.log" 2>&1 || say "  (conv spar echoue)"
read M LO HI N < <(conv_ci "$ART/conv-spar")
say "  conversion 0440 : SPARRING $M  IC95=[$LO,$HI]  (n=$N) [egdbmix=0.302 ; 0468 full-line=0.251 ; Scan=0.95]"
say "  => egdbmix 0.302 $(awk "BEGIN{print ($LO<=0.302 && 0.302<=$HI)?\"DANS\":\"HORS\"}") l'IC ; seuil 'compte' >0.35"
say ""; say "================= LECTURE ================="
say "  SPARRING > 0.35 (egdbmix HORS l'IC, voire vers ~Scan) => la distribution-punie par Scan ENSEIGNE la securite tactique"
say "       => le levier B vit => baseline acquise => derriere : self-play depuis ce champion (independance, etape 7)."
say "  SPARRING ~ 0.30 => meme la punition d'un agent voyant ne prend pas a ce volume/poids => monter volume/poids ou affiner"
say "       le label (positions pre-shot seulement) avant de conclure. (Probe : volume modeste sur box lente.)"
