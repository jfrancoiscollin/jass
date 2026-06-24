#!/usr/bin/env bash
# id: ccx33-0454-egdb-mix
# description: BITBASE-MIX (suite 0453, feu vert JFC). 0453 : le lineaire fitte la WDL finale a 97.3% (vs 88.2% du champion
# base) => gain finale recuperable, sans NNUE. Ici on MIXE de la data egdb-finale (exacte, <=7p) au pool self-play
# (phase-weighte : l'egdb est tout en finale -> ne touche QUE la banque EG, le milieu reste intact), on refit un 32cf, et
# on juge le GAIN REEL : (1) precision finale vs egdb (base vs mix), (2) CONVERSION de finales gagnees vs Scan (le payoff,
# base vs mix), (3) mix vs base 3e-5 en self-play (le mix nuit-il au jeu general ?). Si conversion finale monte ET general
# >= base => on tient un gain endgame propre. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0454-egdb-mix/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-egdbmix; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
GEOM32=/root/jass-geom32-egdbmix
POOL_TRIM=18000000; NEGDB=4000000; NTEST=40000; NCONV=60; L2=3e-5; MAXIT=25; CHUNK=1000000; BAND=40; D=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
# auto-detection egdb (ccx33=/root/egdb_db ou /root/egdb_extracted/app)
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"

say "=== build jass JASS_EGDB=ON ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ_base.pjtw" || { say "ABORT: champion absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# ---------- pool self-play (corpus committe) + egdb finale ----------
say "=== assemble pool self-play (corpus committe) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; tail "$W/assemble.log"|tee -a "$RES"; exit 8; }
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
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool self-play : ${NPOOL}"
say "=== gen egdb : ${NEGDB} (mix) + ${NTEST} test + ${NCONV} conversion (seeds disjoints) ==="
"$JASS" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 2002 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
"$JASS" --gen-egdb-wld "$NTEST" "$W/test.jnnw" "$EGDIR" 7 2048 9999 >"$W/gt.log" 2>&1 || { say "ABORT gen test"; exit 7; }
"$JASS" --gen-egdb-wld 4000     "$W/conv.jnnw" "$EGDIR" 7 2048 7777 >"$W/gc.log" 2>&1 || true

# ---------- mix + fit ----------
say "=== mix (pool + egdb-finale) -> fit 32cf ==="
cp "$W/pool.jnnw" "$W/mixed.jnnw"
python3 - "$W/egdb.jnnw" "$W/mixed.jnnw" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]; acc=sys.argv[2]
raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close()
print(old+n)
PY
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/mixed.jnnw','rb').read(8)[4:8])[0])"); say "  corpus mixe : ${NMIX} (${NPOOL} self-play + ${NEGDB} egdb)"
"$JASS" --dump-eval-features "$W/mixed.jnnw" "$W/mixed.feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/mixed.jnnw" --feat "$W/mixed.feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_mix.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_mix.pjtw" > "$ART/champion-egdbmix.pjtw.gz"
rm -f "$W/mixed.feat"   # libere le gros feat

# ---------- (1) precision finale vs egdb : base vs mix (eval-pur, sans egdb) ----------
say ""; say "=== (1) precision finale vs egdb (eval-pur prof 1) : base vs mix ==="
export JASS="$JASS" BASE="$W/champ_base.pjtw" MIX="$W/champ_mix.pjtw" TESTJ="$W/test.jnnw" BAND="$BAND"
unset JASS_EGDB_PATH
worker(){ SHARD="$1" NS="$2" python3 - <<'PY'
import os,sys,re,struct
sys.path.insert(0,'tools'); from calibrate_vs_scan import JassEngine
JASS=os.environ["JASS"]; BASE=os.environ["BASE"]; MIX=os.environ["MIX"]; TESTJ=os.environ["TESTJ"]; BAND=int(os.environ["BAND"])
SH=int(os.environ["SHARD"]); NS=int(os.environ["NS"]); REC=38
b=open(TESTJ,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
def fen(i):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    return f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}", struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
eb=JassEngine(JASS,pattern_path=BASE,no_book=True); em=JassEngine(JASS,pattern_path=MIX,no_book=True)
def ev(e,f):
    e.set_position_fen(f); e._drain(); e._send("go depth 1")
    L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=20)[-1]
    if L.startswith("error"): return None
    m=re.search(r"score=(-?\d+)",L); return int(m.group(1)) if m else None
ac={"b":[0,0],"m":[0,0]}
for i in range(SH,n,NS):
    f,wdl=fen(i)
    if wdl==0: continue
    for nm,e in (("b",eb),("m",em)):
        s=ev(e,f)
        if s is None: continue
        ac[nm][1]+=1
        if (wdl>0 and s>BAND) or (wdl<0 and s<-BAND): ac[nm][0]+=1
eb.close(); em.close(); print(f"R {ac['b'][0]} {ac['b'][1]} {ac['m'][0]} {ac['m'][1]}")
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/a.$s" 2>&1 & done; wait
python3 - "$W"/a.* <<'PY' | tee -a "$RES"
import sys
b=[0,0]; m=[0,0]
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("R "): v=list(map(int,l.split()[1:5])); b=[b[0]+v[0],b[1]+v[1]]; m=[m[0]+v[2],m[1]+v[3]]
  except: pass
def pc(o,t): return f"{100*o/t:.1f}% ({o}/{t})" if t else "n/a"
print(f"  decisifs finale correct : BASE {pc(b[0],b[1])}   MIX {pc(m[0],m[1])}   (rappel 0453 egdb-only: 97.3%)")
PY

# ---------- (2) conversion finales gagnees vs Scan : base vs mix ----------
say ""; say "=== (2) conversion finales gagnees vs Scan (d${D}, no-DB) : base vs mix ==="
python3 - "$W/conv.jnnw" "$W/conv_open.fen" "$NCONV" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]; cap=int(sys.argv[3]); out=open(sys.argv[2],'w'); k=0
for i in range(n):
    if k>=cap: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]; wdl=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if wdl!=1 or pc<5: continue   # STM gagne, assez de pieces pour une vraie partie
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    out.write(f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}\n"); k+=1
out.close(); print(k)
PY
NCO=$(grep -cvE '^\s*$' "$W/conv_open.fen" 2>/dev/null || echo 0); say "  positions finale gagnees (STM) : ${NCO}"
conv(){ python3 - "$1" "$W/conv_open.fen" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.strip()
    if b: stm[b]=b.split(':',1)[0]
jw=jn=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue   # jass = camp gagnant (STM)
    jw+=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0); jn+=1
print(f"{jw/jn:.3f} ({jw:.0f}/{jn})" if jn else "NA")
PY
}
if [ "${NCO:-0}" -ge 10 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ_base.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$W/conv_open.fen" --dump-games-dir "$ART/conv-base" >"$W/cvb.log" 2>&1 || say "  (conv base echoue)"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ_mix.pjtw"  --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$W/conv_open.fen" --dump-games-dir "$ART/conv-mix"  >"$W/cvm.log" 2>&1 || say "  (conv mix echoue)"
  say "  conversion finale vs Scan : BASE $(conv "$ART/conv-base")   MIX $(conv "$ART/conv-mix")"
else say "  (pas assez de positions finale pour le juge conversion)"; fi

# ---------- (3) mix vs base self-play (le mix nuit-il au general ?) ----------
say ""; say "=== (3) mix vs base 3e-5 en self-play (d9) : le mix nuit-il au jeu general ? ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$JASS" --pattern-a "$W/champ_mix.pjtw" \
    --jass-b "$JASS" --pattern-b "$W/champ_base.pjtw" --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/sp.$s" 2>&1 & done; wait
SP=$(python3 - "$W"/sp.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (mix={a} D={d} base={b})" if g else "NA")
PY
)
say "  mix vs base (self-play d9) : ${SP}   (>=0.5 = le mix ne nuit pas / aide)"
say ""; say "================= LECTURE ================="
say "  (1) MIX > BASE en precision finale ET (2) conversion MIX > BASE vs Scan ET (3) self-play >= 0.5"
say "       => gain endgame PROPRE par bitbase-mix, sans nuire au milieu => champion a promouvoir."
say "  (2) conversion ~ egale => l'eval finale etait deja assez bonne pour la conversion a cette profondeur."
say "=========================================="
