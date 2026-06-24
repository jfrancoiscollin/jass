#!/usr/bin/env bash
# id: ccx33-0455-egdb-push
# description: POUSSER LA FINALE (suite 0454, opt 2 JFC). 0454 : mix 4M egdb-finale => 94.4% precision (plafond egdb-only
# 97.3%), +58 Elo, conversion vs Scan 0.90. Ici on POUSSE : mix 12M egdb (3x) pour se rapprocher du plafond + plus de
# conversion. On compare au champion egdb-mix(4M) de 0454 (le nouveau best) : (1) precision finale vs egdb (3e-5 / mix4M /
# push12M), (2) conversion finales gagnees vs Scan (mix4M vs push12M), (3) push vs mix4M self-play (12M bat-il 4M ?). Plus
# une SONDE de disponibilite des bitbases MTC (distance-to-conversion) -> dit si le futur job 'labels MTC' est ouvert.
# AUCUN NNUE. On ne touche pas a 0442.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0455-egdb-push/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-egdbpush; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
BASE_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
MIX4_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
GEOM32=/root/jass-geom32-egdbpush
POOL_TRIM=15000000; NEGDB=12000000; NTEST=40000; NCONV=80; L2=3e-5; MAXIT=25; CHUNK=1000000; BAND=40; D=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb WLD : $EGDIR"

say "=== build jass JASS_EGDB=ON ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$BASE_GZ" 2>/dev/null | gunzip > "$W/champ_base.pjtw" || { say "ABORT: base absent"; exit 4; }
git show "origin/main:$MIX4_GZ" 2>/dev/null | gunzip > "$W/champ_mix4.pjtw" || { say "ABORT: champion-egdbmix(0454) absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# ---------- sonde MTC (distance-to-conversion) ----------
say "=== sonde bitbases MTC (pour un futur job labels-distance) ==="
MTCDIR=""; for d in /root/egdb_mtc /root/egdb_extracted/mtc /root/egdb_db_mtc /root/egdb_extracted/app; do ls "$d"/*mtc* "$d"/mtc* >/dev/null 2>&1 && { MTCDIR="$d"; break; }; done
if [ -n "$MTCDIR" ]; then
  "$JASS" --egdb-mtc-probe "$EGDIR" "$MTCDIR" 2000 >"$W/mtc.log" 2>&1 && say "  MTC DISPO : $MTCDIR (labels-distance possibles)" || { say "  MTC trouve mais ne s'ouvre pas ($MTCDIR)"; tail -3 "$W/mtc.log"|sed 's/^/    /'; }
else say "  MTC absent (pas de bitbases distance) => le futur job 'labels MTC' devra d'abord les installer ; on reste en WLD."; fi

# ---------- pool + gros egdb ----------
say "=== assemble pool self-play + gen 12M egdb ==="
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
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool self-play : ${NPOOL}"
"$JASS" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 3003 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
"$JASS" --gen-egdb-wld "$NTEST" "$W/test.jnnw" "$EGDIR" 7 2048 9999 >"$W/gt.log" 2>&1 || { say "ABORT gen test"; exit 7; }
"$JASS" --gen-egdb-wld 6000     "$W/conv.jnnw" "$EGDIR" 7 2048 7777 >"$W/gc.log" 2>&1 || true

say "=== mix (pool + 12M egdb) -> fit push ==="
cp "$W/pool.jnnw" "$W/mixed.jnnw"
python3 - "$W/egdb.jnnw" "$W/mixed.jnnw" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]; acc=sys.argv[2]
old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]
o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
PY
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/mixed.jnnw','rb').read(8)[4:8])[0])"); say "  corpus mixe : ${NMIX} (${NPOOL} sp + ${NEGDB} egdb)"
"$JASS" --dump-eval-features "$W/mixed.jnnw" "$W/mixed.feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/mixed.jnnw" --feat "$W/mixed.feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_push.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_push.pjtw" > "$ART/champion-egdbpush12M.pjtw.gz"; rm -f "$W/mixed.feat"

# ---------- (1) precision finale vs egdb : 3 champions ----------
say ""; say "=== (1) precision finale vs egdb (eval-pur prof 1) : 3e-5 / mix4M(0454) / push12M ==="
export JASS="$JASS" P1="$W/champ_base.pjtw" P2="$W/champ_mix4.pjtw" P3="$W/champ_push.pjtw" TESTJ="$W/test.jnnw" BAND="$BAND"; unset JASS_EGDB_PATH
worker(){ SHARD="$1" NS="$2" python3 - <<'PY'
import os,sys,re,struct
sys.path.insert(0,'tools'); from calibrate_vs_scan import JassEngine
JASS=os.environ["JASS"]; PS=[os.environ["P1"],os.environ["P2"],os.environ["P3"]]; TESTJ=os.environ["TESTJ"]; BAND=int(os.environ["BAND"])
SH=int(os.environ["SHARD"]); NS=int(os.environ["NS"]); REC=38
b=open(TESTJ,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
def fen(i):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    return f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}", struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
es=[JassEngine(JASS,pattern_path=p,no_book=True) for p in PS]
def ev(e,f):
    e.set_position_fen(f); e._drain(); e._send("go depth 1")
    L=e._read_until(lambda l:l.startswith("bestmove") or l.startswith("error"),timeout_s=20)[-1]
    if L.startswith("error"): return None
    m=re.search(r"score=(-?\d+)",L); return int(m.group(1)) if m else None
ok=[0,0,0]; tot=[0,0,0]
for i in range(SH,n,NS):
    f,wdl=fen(i)
    if wdl==0: continue
    for j,e in enumerate(es):
        s=ev(e,f)
        if s is None: continue
        tot[j]+=1
        if (wdl>0 and s>BAND) or (wdl<0 and s<-BAND): ok[j]+=1
for e in es: e.close()
print("R "+" ".join(map(str,ok+tot)))
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/a.$s" 2>&1 & done; wait
python3 - "$W"/a.* <<'PY' | tee -a "$RES"
import sys
ok=[0,0,0]; tot=[0,0,0]
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("R "):
        v=list(map(int,l.split()[1:7])); ok=[ok[i]+v[i] for i in range(3)]; tot=[tot[i]+v[i+3] for i in range(3)]
  except: pass
nm=["3e-5","mix4M","push12M"]
for i in range(3):
    print(f"  {nm[i]:>8} decisifs finale : {100*ok[i]/tot[i]:.1f}% ({ok[i]}/{tot[i]})" if tot[i] else f"  {nm[i]}: n/a")
print("  (rappel : 3e-5=88.2%, mix4M=94.4%, plafond egdb-only=97.3%)")
PY

# ---------- (2) conversion vs Scan : mix4M vs push12M ----------
say ""; say "=== (2) conversion finales gagnees vs Scan (d${D}) : mix4M vs push12M ==="
python3 - "$W/conv.jnnw" "$W/conv_open.fen" "$NCONV" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]; cap=int(sys.argv[3]); out=open(sys.argv[2],'w'); k=0
for i in range(n):
    if k>=cap: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]; wdl=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if wdl!=1 or pc<5: continue
    sl=lambda x:[j+1 for j in range(50) if (x>>j)&1]
    out.write(f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}\n"); k+=1
out.close(); print(k)
PY
NCO=$(grep -cvE '^\s*$' "$W/conv_open.fen" 2>/dev/null || echo 0); say "  positions finale gagnees : ${NCO}"
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
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    jw+=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0); jn+=1
print(f"{jw/jn:.3f} ({jw:.0f}/{jn})" if jn else "NA")
PY
}
if [ "${NCO:-0}" -ge 10 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ_mix4.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$W/conv_open.fen" --dump-games-dir "$ART/conv-mix4" >"$W/cv4.log" 2>&1 || say "  (conv mix4 echoue)"
  python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ_push.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$W/conv_open.fen" --dump-games-dir "$ART/conv-push" >"$W/cvp.log" 2>&1 || say "  (conv push echoue)"
  say "  conversion finale vs Scan : mix4M $(conv "$ART/conv-mix4")   push12M $(conv "$ART/conv-push")"
else say "  (pas assez de positions finale)"; fi

# ---------- (3) push vs mix4M self-play ----------
say ""; say "=== (3) push12M vs mix4M self-play (d9) : plus d'egdb gagne-t-il ? ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$JASS" --pattern-a "$W/champ_push.pjtw" \
    --jass-b "$JASS" --pattern-b "$W/champ_mix4.pjtw" --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/sp.$s" 2>&1 & done; wait
SP=$(python3 - "$W"/sp.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (push={a} D={d} mix4={b})" if g else "NA")
PY
)
say "  push12M vs mix4M (self-play d9) : ${SP}   (>0.5 = plus d'egdb aide encore)"
say ""; say "================= LECTURE ================="
say "  push12M > mix4M (precision + conversion + self-play) => continuer a augmenter l'egdb (vers le plafond 97%)."
say "  push12M ~ mix4M => 4M saturait deja la banque finale => le gain WLD est PRIS ; pour aller plus loin = labels MTC (distance)."
say "=========================================="
