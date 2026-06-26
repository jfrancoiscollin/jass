#!/usr/bin/env bash
# id: ccx33-0474-deepscale-bootstrap
# description: LE DECIDEUR du programme lineaire (ajout A du memo JFC 2026-06-25) — deep-relabel ITERE en BOOTSTRAP, juge sur
# la COURBE D'ASYMPTOTE (pas un probe unique). Cap honnete : un relabel ne punit que les ~52% de shots que le pilote VOIT a
# d16 => un seul probe >0.35 ne prouve rien de structurel. La vraie question : le relabel ITERE (pilote plus fort -> punit
# plus -> relabel -> refit) GRIMPE-t-il vers >=0.70 (C3, linaire gagne) ou CALE-t-il ~0.52 (borne par la vue de jass, pas par
# la classe) ? On instrumente pass-apres-pass : a chaque passe, re-etiqueter un echantillon FRAIS de milieu par recherche d16
# avec le PILOTE COURANT (egdbmix au depart, puis le champion de la passe precedente) -> fit -> juge 0440 + IC95 + FLIP%. La
# suite {0440_p1, 0440_p2, ...} est committee (curve.txt + conv-pass$k, survit au non-flush). Declenche si 0465 boucle 1 flat
# (directive JFC). Lecture : asymptote >=0.70 = NNUE jamais necessaire ; asymptote ~0.52 = passer au levier B (sparring-vs-Scan,
# C2-(4)) AVANT tout NNUE. 100% lineaire, SANS Scan dans le label, SANS NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0474-deepscale-bootstrap/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
CURVE="$ART/curve.txt"; : > "$CURVE"
W=/root/cw-bootstrap74; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-bootstrap74
POOL_TRIM=12000000; NEGDB=4000000; NSAMPLE=350000; RELABEL_DEPTH=16; DRAW_BAND=20; MID_LO=12; MID_HI=44; TARGET_FRAC=25; KPASS=3
# DIM BOX LENTE (ccx33, JFC : garder 0465 sur cpx62) : d16 (d18 trop lent ici), echantillon 350k, 3 passes, pool 12M
# -> faisable ~1-1.5j. Garde la bande-nulle 20 (le vrai fix du FLIP 0472 : band50 DRAWIFIE ~35% des
# labels et noie le signal-shot a 3.4%) ; NSAMPLE 800k->600k pour compenser le cout de d18. Pruning-OFF dispo via le nouveau
# --search-params du tool si le bootstrap cale (trop lent pour 4 passes full-width ; garde pour un probe cible).
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — juge 0440 a faire ailleurs)"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR ; KPASS=$KPASS ; NSAMPLE=$NSAMPLE ; relabel d$RELABEL_DEPTH"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot absent"; exit 4; }
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

say "=== assemble pool (${POOL_TRIM}) + gen egdb (${NEGDB}) une fois ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8012 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }

PILOT="$W/pilot.pjtw"        # passe 1 = egdbmix ; ensuite = champion de la passe precedente (BOOTSTRAP)
say "pass 0  pilote=egdbmix  baseline 0440=0.302  cap-vue-jass~0.52  seuil-C3=0.70" | tee -a "$CURVE"
for k in $(seq 1 "$KPASS"); do
  say ""; say "================= PASSE $k / $KPASS (pilote = $([ "$k" = 1 ] && echo egdbmix || echo champion-passe-$((k-1)))) ================="
  # 1) echantillon FRAIS de milieu -> shards
  python3 - "$W/pool.jnnw" "$W/s$k" "$NSAMPLE" "$MID_LO" "$MID_HI" "$NCPU" "$k" <<'PY' | tee -a "$RES"
import struct,sys,random; REC=38
pool,pre,cap,lo,hi,nsh,k=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6]),int(sys.argv[7])
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
random.seed(100+k); idx=list(range(n)); random.shuffle(idx); recs=[]
for i in idx:
    r=bytes(body[i*REC:(i+1)*REC]); wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: recs.append(r)
    if len(recs)>=cap: break
sh=[bytearray() for _ in range(nsh)]; cnt=[0]*nsh
for j,r in enumerate(recs): sh[j%nsh]+=r; cnt[j%nsh]+=1
for s in range(nsh): open(f"{pre}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',cnt[s])+bytes(sh[s]))
print(f"  passe {k} : echantillon milieu frais = {len(recs)} ({nsh} shards)")
PY
  # 2) deep-relabel parallele avec le PILOTE courant
  for s in $(seq 0 $((NCPU-1))); do
    "$J" --deep-relabel "$W/s$k.$s.jnnw" "$W/s$k.$s.deep.jnnw" "$RELABEL_DEPTH" --nnue "$PILOT" --egdb "$EGDIR" --draw-band "$DRAW_BAND" --cache-mb 512 >"$W/rl$k.$s.log" 2>&1 &
  done; wait
  python3 - "$W/deep$k.jnnw" "$W/s$k" "$NCPU" "$ART/FLIP_pass$k.txt" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
out=sys.argv[1]; pre=sys.argv[2]; nsh=int(sys.argv[3]); flipout=sys.argv[4]
body=bytearray(); tot=0; flip=same=0; dist={-1:0,0:0,1:0}
for s in range(nsh):
    try: sh=open(f"{pre}.{s}.jnnw",'rb').read(); dp=open(f"{pre}.{s}.deep.jnnw",'rb').read()
    except FileNotFoundError: continue
    ns=struct.unpack('<I',sh[4:8])[0]; nd=struct.unpack('<I',dp[4:8])[0]
    sb=memoryview(sh)[8:8+ns*REC]; db=memoryview(dp)[8:8+nd*REC]; body+=bytes(db); tot+=nd
    for i in range(min(ns,nd)):
        w0=struct.unpack('<b',sb[i*REC+37:i*REC+38])[0]; w1=struct.unpack('<b',db[i*REC+37:i*REC+38])[0]
        dist[w1]=dist.get(w1,0)+1
        if w0==w1: same+=1
        else: flip+=1
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); g=flip+same
open(flipout,'w').write(f"flip={flip} same={same} pct={100*flip/max(g,1):.1f} L={dist.get(-1,0)} D={dist.get(0,0)} W={dist.get(1,0)} total={tot}\n")
print(f"  passe : relabel {tot} ; FLIP={100*flip/max(g,1):.0f}% [deep L={dist.get(-1,0)} D={dist.get(0,0)} W={dist.get(1,0)}]")
PY
  rm -f "$W"/s$k.*.jnnw "$W"/s$k.*.deep.jnnw
  ND=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/deep$k.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
  [ "${ND:-0}" -ge 50000 ] || { say "  ABORT passe $k : relabel vide ($ND)"; tail -4 "$W"/rl$k.0.log|sed 's/^/    /'; exit 7; }
  # 3) corpus = pool + egdb + deep (sur-pondere ~TARGET_FRAC%) ; fit
  REP=$(python3 -c "p=$POOL_TRIM+$NEGDB; f=$TARGET_FRAC/100.0; import math; print(max(1,math.ceil(f/(1-f)*p/$ND)))")
  python3 - "$W/deep$k.jnnw" "$W/deepH$k.jnnw" "$REP" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',n*int(sys.argv[3]))+body*int(sys.argv[3]))
PY
  cp "$W/pool.jnnw" "$W/corpus$k.jnnw"; app "$W/egdb.jnnw" "$W/corpus$k.jnnw" >/dev/null; app "$W/deepH$k.jnnw" "$W/corpus$k.jnnw" >/dev/null
  rm -f "$W/deepH$k.jnnw"
  "$J" --dump-eval-features "$W/corpus$k.jnnw" "$W/feat$k" >"$W/feat$k.log" 2>&1 || { say "ABORT dump feat p$k"; exit 8; }
  env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus$k.jnnw" --feat "$W/feat$k" \
      --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ$k.pjtw" >"$W/fit$k.log" 2>&1 || { say "TRAIN FAIL p$k"; tail -6 "$W/fit$k.log"|sed 's/^/  /'; exit 9; }
  rm -f "$W/feat$k" "$W/corpus$k.jnnw"
  gzip -c "$W/champ$k.pjtw" > "$ART/champion-bootstrap-pass$k.pjtw.gz"
  # 4) juge 0440 vs Scan (depth-fixe) + IC95 ; ecrit la COURBE
  if [ "$HAVE_SCAN" = 1 ]; then
    JE="$W/champ$k.pjtw"; ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$JE" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-pass$k" >"$W/cv$k.log" 2>&1 ) || say "  (juge p$k echoue)"
    read M LO HI N < <(conv_ci "$ART/conv-pass$k")
    FLIP=$(grep -oE "pct=[0-9.]+" "$ART/FLIP_pass$k.txt" 2>/dev/null | cut -d= -f2)
    say "pass $k  0440=$M  IC95=[$LO,$HI]  FLIP=${FLIP}%  (n=$N ; egdbmix 0.302 $(awk "BEGIN{print ($LO<=0.302 && 0.302<=$HI)?\"DANS\":\"HORS\"}") l'IC)" | tee -a "$CURVE"
  else say "pass $k  (Scan absent : champion committe, juge 0440 a faire ailleurs)" | tee -a "$CURVE"; fi
  PILOT="$W/champ$k.pjtw"   # BOOTSTRAP : le champion de cette passe pilote le relabel suivant
done

say ""; say "================= COURBE D'ASYMPTOTE (le decideur) ================="
cat "$CURVE" | sed 's/^/  /' | tee -a "$RES"
say ""; say "  LECTURE :"
say "   suite {0440_p1..pK} GRIMPE vers >=0.70  => le linaire GAGNE (bootstrap converge au-dessus de C3) => NNUE jamais necessaire."
say "   suite CALE ~0.52 (plateau, IC se chevauchent) => borne par la VUE de jass (~52% des shots), PAS par la classe"
say "        => passer au levier B = SPARRING vs Scan (labels resultat reel, C2-(4)) AVANT toute ouverture NNUE."
say "   suite plate ~0.30 => meme le relabel profond ne prend pas (FLIP% faible ? depth ? volume ?) => creuser avant de conclure."
