#!/usr/bin/env bash
# id: ccx33-0458-tactical-supervision
# description: FLUX DE SUPERVISION TACTIQUE (feu vert JFC — attaque directe du 25%->). Insight : nos defaites sont des
# lignes FORCEES (2-6 plis, dans l'horizon) => recherche profonde + quiescence RESOUT le materiel en verite-terrain, PAS
# borne par l'eval => ce N'EST PAS de la distillation. Le self-play WDL MAL-ETIQUETTE ces positions (jass convertit 25% =>
# label 'gagnant' faux 75% du temps). Lever : miner des positions de milieu (pool self-play + milieux lidraughts), les
# RE-LABELLISER par jass d14 + EGDB (--deep-relabel, verite-terrain sur la ligne forcee), reperer les CORRECTIONS (deep-WDL
# != WDL self-play = les positions tactiques mal-etiquetees), les SUR-PONDERER (x4) dans le fit WDL, refit, et juger sur le
# gate 0440 (conversion combinaisons vs Scan). Pilote/leaf-eval = champion-egdbmix. Sans Scan. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0458-tactical-supervision/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-tacsup; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
GEOM32=/root/jass-geom32-tacsup
POOL_TRIM=15000000; NEGDB=4000000; NTAC=300000; RELABEL_D=14; MID_LO=14; MID_HI=40; OVERSAMPLE=4
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11; JUDGE_PAIRS=28
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot egdbmix absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

# ---------- pool self-play + egdb (recette de base) ----------
say "=== assemble pool + egdb (base) ==="
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

# ---------- mine ~300k positions de MILIEU (pool + lidraughts) ----------
say "=== mine ${NTAC} positions de milieu (${MID_LO}-${MID_HI} pieces) a re-labelliser ==="
python3 - "$W/pool.jnnw" "$W/tac.jnnw" "$NTAC" "$MID_LO" "$MID_HI" $SHARDS <<'PY' | tee -a "$RES"
import struct,sys,random,gzip; REC=38
pool,out,cap,lo,hi=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]); shards=sys.argv[6:]
random.seed(7)
def midf(buf,n):
    res=[]
    for i in range(n):
        r=buf[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: res.append(bytes(r))
    return res
mids=[]
b=open(pool,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
# echantillonne le pool : 1 sur k pour ne pas tout scanner
idx=list(range(n)); random.shuffle(idx);
for i in idx[:cap*3]:
    r=bytes(body[i*REC:(i+1)*REC]); wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: mids.append(r)
    if len(mids)>=cap*8//10: break
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; mids+=midf(memoryview(raw)[8:8+m*REC],m)
    if len(mids)>=cap: break
random.shuffle(mids); mids=mids[:cap]
open(out,'wb').write(b'JNNW'+struct.pack('<I',len(mids))+b''.join(mids)); print(f"  mine : {len(mids)} positions milieu")
PY
# garde une COPIE des WDL d'origine (self-play / lidraughts) pour reperer les corrections
cp "$W/tac.jnnw" "$W/tac_orig.jnnw"

# ---------- re-labellise par recherche profonde d14 + EGDB (sharde) ----------
say "=== deep-relabel d${RELABEL_D} + EGDB (verite-terrain sur lignes forcees, sharde) ==="
python3 - "$W/tac.jnnw" "$W/sh" "$NCPU" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]; pre=sys.argv[2]; k=int(sys.argv[3]); per=(n+k-1)//k
for s in range(k):
    a=s*per; z=min(a+per,n); m=max(0,z-a)
    open(f"{pre}.{s}",'wb').write(b'JNNW'+struct.pack('<I',m)+bytes(body[a*REC:z*REC]))
PY
for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/sh.$s" "$W/sho.$s" "$RELABEL_D" --nnue "$W/pilot.pjtw" --egdb "$EGDIR" >/dev/null 2>&1 & done; wait
python3 - "$W/tac_lbl.jnnw" "$W/sho" "$NCPU" <<'PY'
import struct,sys; REC=38; out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); body=b""; tot=0
for s in range(k):
    try: b=open(f"{pre}.{s}",'rb').read()
    except FileNotFoundError: continue
    if b[:4]!=b'JNNW': continue
    m=struct.unpack('<I',b[4:8])[0]; tot+=m; body+=b[8:8+m*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
rm -f "$W"/sh.* "$W"/sho.*

# ---------- corrections (deep-WDL != WDL d'origine) + sur-echantillonnage ----------
say "=== corrections (deep-WDL != self-play WDL) -> sur-pondere x${OVERSAMPLE} ==="
python3 - "$W/tac_orig.jnnw" "$W/tac_lbl.jnnw" "$W/tac_final.jnnw" "$OVERSAMPLE" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
orig=open(sys.argv[1],'rb').read(); lbl=open(sys.argv[2],'rb').read(); out=sys.argv[3]; ov=int(sys.argv[4])
n=struct.unpack('<I',lbl[4:8])[0]; ob=memoryview(orig)[8:8+n*REC]; lb=memoryview(lbl)[8:8+n*REC]
res=bytearray(); corr=0
for i in range(n):
    ro=ob[i*REC:(i+1)*REC]; rl=lb[i*REC:(i+1)*REC]
    wo=struct.unpack('<b',ro[37:38])[0]; wl=struct.unpack('<b',rl[37:38])[0]
    res+=bytes(rl)                                  # toujours la version deep-relabel (verite-terrain)
    if wl!=wo:                                      # correction tactique => sur-pondere
        corr+=1
        for _ in range(ov-1): res+=bytes(rl)
tot=len(res)//REC
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(res)); print(f"  corrections={corr}/{n} ({100*corr/n:.1f}%) ; flux tactique total (avec oversample)={tot}")
PY

# ---------- corpus final = pool + egdb + flux tactique ; fit ----------
say "=== fit : pool + egdb-finale + flux tactique sur-pondere ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 6006 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/tac_final.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])"); say "  corpus final : ${NMIX}"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_tac.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_tac.pjtw" > "$ART/champion-tactical.pjtw.gz"; rm -f "$W/feat"
unset JASS_EGDB_PATH

# ---------- GATE 0440 : conversion combinaisons vs Scan ----------
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
say ""; say "=== GATE 0440 : conversion combinaisons vs Scan (d${D}) — tactical vs egdbmix ==="
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/pilot.pjtw"     --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-egdbmix" >"$W/ce.log" 2>&1 || say "  (conv egdbmix echoue)"
python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_tac.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-tac" >"$W/ct.log" 2>&1 || say "  (conv tac echoue)"
say "  conversion 0440 : egdbmix $(conv "$ART/conv-egdbmix")   TACTICAL $(conv "$ART/conv-tac")   (cible : 0.246 -> ? ; Scan 0.95)"
say "  self-direct : tactical vs egdbmix = $(pjudge "$W/champ_tac.pjtw" "$W/pilot.pjtw")"
say ""; say "================= LECTURE ================="
say "  conversion 0440 TACTICAL >> egdbmix => la supervision tactique attaque le mode d'echec (le label corrige paie)"
say "       => promouvoir + baker le flux tactique dans la recette. PREMIER levier qui vise le MILIEU directement."
say "  conversion ~ egale => les corrections deep-d${RELABEL_D} ne suffisent pas (jass-deep rate trop de shots, cf 0445)"
say "       => monter RELABEL_D, ou mining cible par detecteurs dilf, ou (gate) signal feature (cf 0457)."
say "=========================================="
