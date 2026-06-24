#!/usr/bin/env bash
# id: cpx62-0462-tactical-shotfilter
# description: SUPERVISION TACTIQUE v2 — FIX du 0460 (qui relabellisait TOUT le milieu = self-distillation, -recul). Ici on
# FILTRE aux VRAIES positions a shot : pour chaque position de milieu, on score par une recherche ELAGAGE OFF (full-width,
# qui EXPLORE le sacrifice + deroule les prises forcees en quiescence) a faible profondeur (d6) => on ne garde QUE celles ou
# il existe un gain materiel FORCE >=2 pions (|score|>=170 = verite-terrain, independante de la force de l'eval). On les
# labelise WDL=signe(score) (attaque ET defense), on sur-pondere x4, on mixe au pool+egdb, on refit, on juge sur 0440. C'est
# la supervision tactique CORRECTE : labels exacts sur lignes forcees seulement, pas du positionnel borne. Sans Scan requis
# (HUB --search-params OFF) ; gate 0440 si Scan present. Pilote/leaf = champion-egdbmix. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0462-tactical-shotfilter/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-shotf; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
GEOM32=/root/jass-geom32-shotf
POOL_TRIM=18000000; NEGDB=4000000; NMINE=800000; SHOT_DEPTH=6; SHOT_THR=170; MID_LO=14; MID_HI=40; OVERSAMPLE=4
OFF="rfp_max_depth=0,nmp_min_depth=99,lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,multicut_min_depth=0,probcut_min_depth=0"
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11; JUDGE_PAIRS=28
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire sur ccx33)"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

say "=== assemble pool + mine ${NMINE} positions de milieu ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
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
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W/pool.jnnw" "$W/mine.jnnw" "$NMINE" "$MID_LO" "$MID_HI" $SHARDS <<'PY' | tee -a "$RES"
import struct,sys,random,gzip; REC=38
pool,out,cap,lo,hi=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]); shards=sys.argv[6:]
random.seed(11); mids=[]
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
idx=list(range(n)); random.shuffle(idx)
for i in idx:
    r=bytes(body[i*REC:(i+1)*REC]); wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: mids.append(r)
    if len(mids)>=cap*7//10: break
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; bd=memoryview(raw)[8:8+m*REC]
    for i in range(m):
        r=bd[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: mids.append(bytes(r))
    if len(mids)>=cap: break
random.shuffle(mids); mids=mids[:cap]
open(out,'wb').write(b'JNNW'+struct.pack('<I',len(mids))+b''.join(mids)); print(f"  mine : {len(mids)}")
PY

say "=== SHOT-FILTER : recherche elagage OFF d${SHOT_DEPTH}, garde |score|>=${SHOT_THR} (shot materiel force >=2 pions) ==="
export JASS="$J" CHAMP="$W/pilot.pjtw" MINE="$W/mine.jnnw" OFF="$OFF" SDEP="$SHOT_DEPTH" STHR="$SHOT_THR"
worker(){ SHARD="$1" NS="$2" python3 - <<'PY'
import os,sys,re,struct
sys.path.insert(0,'tools'); from calibrate_vs_scan import JassEngine
JASS=os.environ["JASS"]; CHAMP=os.environ["CHAMP"]; MINE=os.environ["MINE"]; OFF=os.environ["OFF"]
SDEP=int(os.environ["SDEP"]); STHR=int(os.environ["STHR"]); SH=int(os.environ["SHARD"]); NS=int(os.environ["NS"]); REC=38
b=open(MINE,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
def fen(r):
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    return f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}"
e=JassEngine(JASS, pattern_path=CHAMP, no_book=True, search_params=OFF)
out=open(f"{MINE}.shot.{SH}","wb")
for i in range(SH,n,NS):
    r=bytes(body[i*REC:(i+1)*REC]); f=fen(r)
    e.set_position_fen(f); e._drain(); e._send(f"go depth {SDEP}")
    try: L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=60)[-1]
    except Exception: continue
    m=re.search(r"score=(-?\d+)",L)
    if not m: continue
    sc=int(m.group(1))
    if abs(sc)>=STHR:                       # shot : gain materiel force >=2 pions (full-width)
        wdl=1 if sc>0 else -1
        nr=bytearray(r); nr[37]=struct.pack('<b',wdl)[0]; out.write(bytes(nr))
e.close(); out.close()
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/w.$s.log" 2>&1 & done; wait
python3 - "$W/shots.jnnw" "$W/mine.jnnw.shot" "$NCPU" "$OVERSAMPLE" <<'PY' | tee -a "$RES"
import struct,sys,glob; REC=38
out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); ov=int(sys.argv[4]); body=bytearray(); tot=0
for s in range(k):
    try: b=open(f"{pre}.{s}",'rb').read()
    except FileNotFoundError: continue
    m=len(b)//REC
    for _ in range(ov): body+=b; tot+=m
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  shots trouves={tot//ov} ; flux tactique (oversample x{ov})={tot}")
PY
NS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/shots.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${NS:-0}" -ge 1000 ] || { say "  (trop peu de shots: ${NS} — augmenter NMINE ou baisser SHOT_THR)"; }

say "=== fit : pool + egdb-finale + flux SHOTS sur-pondere ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8008 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/shots.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])"); say "  corpus final : ${NMIX}"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_shot.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_shot.pjtw" > "$ART/champion-shotfilter.pjtw.gz"; rm -f "$W/feat"
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
pjudge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" --jass-b "$J" --pattern-b "$2" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
  python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}" if g else "NA")
PY
  rm -f "$W"/j.* ; }
say ""; say "=== self-direct + GATE 0440 ==="
say "  self-direct : shotfilter vs egdbmix = $(pjudge "$W/champ_shot.pjtw" "$W/pilot.pjtw")"
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/pilot.pjtw"     --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-egdbmix" >"$W/ce.log" 2>&1 || say "  (conv egdbmix echoue)"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_shot.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-shot" >"$W/cs.log" 2>&1 || say "  (conv shot echoue)"
  say "  conversion 0440 : egdbmix $(conv "$ART/conv-egdbmix")   SHOTFILTER $(conv "$ART/conv-shot")   (rappel : egdbmix~0.302 ; Scan 0.95)"
else say "  GATE 0440 : Scan absent => champion committe ; conversion 0440 sur ccx33."; fi
say ""; say "================= LECTURE ================="
say "  SHOTFILTER > egdbmix sur 0440 ET self-direct >=0.5 => la supervision tactique CORRECTE (shots seulement) paie"
say "       => promouvoir + baker. Branche FIT confirmee (les donnees attaquent le milieu)."
say "  ~ egal => meme avec le filtre, les labels-shot ne suffisent pas => probable signal FEATURE (cf 0461) ou monter le volume de shots."
say "=========================================="
