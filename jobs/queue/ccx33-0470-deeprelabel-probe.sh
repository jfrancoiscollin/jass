#!/usr/bin/env bash
# id: ccx33-0470-deeprelabel-probe
# description: LEVIER-FIT PRINCIPAL (successeur de 0465) : la profondeur de JEU, pas le volume. Diagnostic JFC : notre point
# fixe est bas parce que notre self-play (pilote shot-aveugle, joue a d8-d12) ne PUNIT jamais les shots => le label WDL
# n'enseigne pas la securite tactique. Scan prouve que des poids shot-safe EXISTENT dans notre classe (32cf superset de 8cf)
# => ce n'est PAS un plafond de features, c'est la DISTRIBUTION des labels. FIX sans Scan : RE-ETIQUETER un echantillon de
# milieu par une recherche PROFONDE d16 (ou jass punit deja ~52%% des shots, cf 0451 movetime) -> wdl=signe(valeur d16),
# bande-nulle +-50, ancre egdb. Puis fit (pool + egdb + flux deep sur-pondere) -> juge 0440 + IC95 vs egdbmix (0.302). Si
# deep >> 0.35 (hors IC) => les labels profonds enseignent la securite tactique => on monte vers ~0.52 (le plafond de NOTRE
# recherche) => scaler sur cpx62 a d18-20. Si ~0.30 => meme les labels profonds ne bougent rien (surprenant, a creuser).
# C'est le CORRECTIF de 0462 (qui filtrait a d6 = trop superficiel). 100%% lineaire, sans Scan, sans NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0470-deeprelabel-probe/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-deeprl; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-deeprl
POOL_TRIM=12000000; NEGDB=4000000; NSAMPLE=500000; RELABEL_DEPTH=16; MID_LO=12; MID_HI=44; TARGET_FRAC=25
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire ailleurs)"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
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

say "=== assemble pool (${POOL_TRIM}) + echantillon milieu ${NSAMPLE} -> ${NCPU} shards pour relabel parallele ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
python3 - "$W/pool.jnnw" "$W/sample" "$NSAMPLE" "$MID_LO" "$MID_HI" "$NCPU" <<'PY' | tee -a "$RES"
import struct,sys,random; REC=38
pool,pre,cap,lo,hi,k=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6])
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
random.seed(20); idx=list(range(n)); random.shuffle(idx); recs=[]
for i in idx:
    r=bytes(body[i*REC:(i+1)*REC]); wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: recs.append(r)
    if len(recs)>=cap: break
# shards round-robin
sh=[bytearray() for _ in range(k)]; cnt=[0]*k
for j,r in enumerate(recs): sh[j%k]+=r; cnt[j%k]+=1
for s in range(k): open(f"{pre}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',cnt[s])+bytes(sh[s]))
print(f"  echantillon milieu : {len(recs)} positions -> {k} shards (~{len(recs)//k}/shard)")
PY

say "=== DEEP-RELABEL parallele : recherche d${RELABEL_DEPTH} (eval=egdbmix) + ancre egdb, wdl=signe(valeur), bande-nulle +-50 ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --deep-relabel "$W/sample.$s.jnnw" "$W/sample.$s.deep.jnnw" "$RELABEL_DEPTH" --nnue "$W/champ.pjtw" --egdb "$EGDIR" --cache-mb 512 >"$W/rl.$s.log" 2>&1 &
done; wait
# merge + mesure du FLIP (combien de labels ont change vs l'original shallow)
python3 - "$W/deep.jnnw" "$W/sample" "$NCPU" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); body=bytearray(); tot=0
flip=same=0; dist={-1:0,0:0,1:0}
for s in range(k):
    try:
        sh=open(f"{pre}.{s}.jnnw",'rb').read(); dp=open(f"{pre}.{s}.deep.jnnw",'rb').read()
    except FileNotFoundError: continue
    ns=struct.unpack('<I',sh[4:8])[0]; nd=struct.unpack('<I',dp[4:8])[0]
    sb=memoryview(sh)[8:8+ns*REC]; db=memoryview(dp)[8:8+nd*REC]
    body+=bytes(db); tot+=nd
    m=min(ns,nd)
    for i in range(m):
        w0=struct.unpack('<b',sb[i*REC+37:i*REC+38])[0]; w1=struct.unpack('<b',db[i*REC+37:i*REC+38])[0]
        dist[w1]=dist.get(w1,0)+1
        if w0==w1: same+=1
        else: flip+=1
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body))
g=flip+same
print(f"  relabel : {tot} positions ; FLIP vs shallow = {flip}/{g} ({100*flip/max(g,1):.0f}%)  [deep wdl: L={dist.get(-1,0)} D={dist.get(0,0)} W={dist.get(1,0)}]")
print(f"  (un FLIP eleve = la recherche profonde corrige beaucoup de labels shallow-faux => le levier a de la matiere)")
PY
ND=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/deep.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${ND:-0}" -ge 50000 ] || { say "ABORT: relabel quasi vide (${ND}) — voir rl.*.log"; tail -5 "$W"/rl.0.log|sed 's/^/  /'; exit 7; }
cp "$W/deep.jnnw" "$ART/deep_sample.jnnw" 2>/dev/null || true

say "=== fit : pool + egdb + flux DEEP-RELABEL sur-pondere (~${TARGET_FRAC}%) ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8011 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
REP=$(python3 -c "p=$POOL_TRIM+$NEGDB; f=$TARGET_FRAC/100.0; import math; print(max(1,math.ceil(f/(1-f)*p/$ND)))")
python3 - "$W/deep.jnnw" "$W/deep_heavy.jnnw" "$REP" <<'PY'
import struct,sys; REC=38
src,dst,k=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',n*k)+body*k); print(n*k)
PY
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/deep_heavy.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])")
NDH=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/deep_heavy.jnnw','rb').read(8)[4:8])[0])")
say "  corpus : ${NMIX}  (deep ${NDH} = $((100*NDH/NMIX))% ; uniques=${ND}, replique x${REP}, depth ${RELABEL_DEPTH})"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_deep.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_deep.pjtw" > "$ART/champion-deeprelabel.pjtw.gz"; rm -f "$W/feat"
unset JASS_EGDB_PATH

conv(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
jw=jn=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    jw+=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0); jn+=1
print(f"{jw/jn:.3f} ({jw:.0f}/{jn})" if jn else "NA")
PY
}
say ""; say "=== GATE 0440 : deep-relabel vs Scan (DILF complet, d${D}, 1 juge) + IC95 ==="
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_deep.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-deep" >"$W/cd.log" 2>&1 || say "  (conv deep echoue)"
  say "  conversion 0440 : DEEP-RELABEL(d${RELABEL_DEPTH}) $(conv "$ART/conv-deep")   [etablis : egdbmix=0.302 ; 0468 full-line=0.251 ; Scan=0.95 ; cible-recherche-jass ~0.52]"
  python3 - "$ART/conv-deep" "$DILF" <<'PY' | tee -a "$RES"
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
if n:
    m=sum(aw)/n; seed=12345; boots=[]
    for _ in range(2000):
        acc=0
        for _ in range(n):
            seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
        boots.append(acc/n)
    boots.sort(); lo=boots[50]; hi=boots[1949]
    print(f"  IC95 deep-relabel : {m:.3f} [{lo:.3f},{hi:.3f}] (n={n})  => egdbmix 0.302 {'DANS' if lo<=0.302<=hi else 'HORS'} l'IC")
PY
else say "  GATE 0440 : Scan absent => champion committe."; fi
say ""; say "================= LECTURE ================="
say "  deep > 0.35 (egdbmix HORS l'IC, vers ~0.52) => LES LABELS PROFONDS ENSEIGNENT LA SECURITE TACTIQUE : le levier-fit VIT"
say "       => scaler sur cpx62 (d18-20, plus de positions) + iterer le relabel (pilote ameliore -> punit plus de shots)."
say "  deep ~ 0.30 => meme la recherche profonde ne corrige pas le fit a ce poids => creuser (depth plus haute / pruning-off"
say "       pendant le relabel / volume) avant de conclure. FLIP%% (ci-dessus) dit si le relabel avait de la matiere."
say "=========================================="
