#!/usr/bin/env bash
# id: ccx33-0468-fullline-fullvol
# description: FULL-LINE a VOLUME PLEIN (corrige le doute-volume JFC sur 0466/0467). 0466/0467 montaient le poids des combos
# a 35%% en RETRECISSANT le pool a 5M => base SOUS-SATURATION (la famine de fit que tout le programme fuit, lecon 0401) => le
# plat n'etait pas concluant. Ici: pool PLEIN 18M (saturation, APPARIE a egdbmix=18M+4M qui sert de controle sans-combos,
# 0.302) + 4M egdb ; les combos full-line sont montees a ~35%% par REPLICATION (pool JAMAIS reduit). On emet TOUTE la ligne
# forcante [racine..resolution] de vraies parties, label=resultat reel POV trait (noeuds materiel-en-bas inclus). 1 fit, 1
# juge full-line vs Scan sur DILF complet + bootstrap IC95 (pour ne pas surlire le bruit a 305 positions, SE~0.026). Si
# full-line >> 0.31 (hors IC d'egdbmix) => le levier vit ; si ~0.31 => 5e echec a VOLUME PROPRE => plafond FEATURE solide.
# AUCUN moteur dans le label. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0468-fullline-fullvol/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-flinevol; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
DB=/root/jass/data/expert_games.db
GEOM32=/root/jass-geom32-flinevol
POOL_TRIM=18000000; NEGDB=4000000; TARGET_FRAC=35; MID_LO=12; MID_HI=44
WINDOW=12; NET_MIN=2; SAC_MIN=1; CAP_PER_GAME=8; MAX_GAMES=200000; MIN_RATING=1600
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire ailleurs)"
[ -f "$DB" ] || { say "ABORT: expert_games.db absent ($DB) — relancer ccx33-0438 d'abord."; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
NG=$(python3 -c "import sqlite3;print(sqlite3.connect('file:$DB?mode=ro',uri=True).execute(\"select count(*) from expert_games where result in ('1-0','0-1')\").fetchone()[0])" 2>/dev/null || echo 0)
say "  DB : ${NG} parties decisives"
[ "${NG:-0}" -ge 2000 ] || { say "ABORT: trop peu de parties decisives (${NG})."; exit 4; }
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

say "=== assemble pool (reduit ${POOL_TRIM}) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"

say "=== MINE lignes forcantes COMPLETES (sac->regain net >=${NET_MIN} ; emet [racine..resolution], label=resultat reel POV trait) ==="
export JASS="$J" DB="$DB" WINDOW="$WINDOW" NET_MIN="$NET_MIN" SAC_MIN="$SAC_MIN" CAP_PER_GAME="$CAP_PER_GAME" \
       MID_LO="$MID_LO" MID_HI="$MID_HI" MAX_GAMES="$MAX_GAMES" MIN_RATING="$MIN_RATING"
worker(){ SHARD="$1" NS="$2" python3 - <<'PY'
import os,sys,struct
sys.path.insert(0,'tools')
from pdn_to_jnnw import JassOracle, extract_moves, _strip_tags_and_comments, fen_to_bitboards
import sqlite3, logging
JASS=os.environ["JASS"]; DB=os.environ["DB"]
WIN=int(os.environ["WINDOW"]); NET=int(os.environ["NET_MIN"]); SAC=int(os.environ["SAC_MIN"])
CAP=int(os.environ["CAP_PER_GAME"]); LO=int(os.environ["MID_LO"]); HI=int(os.environ["MID_HI"])
MAXG=int(os.environ["MAX_GAMES"]); MINR=int(os.environ["MIN_RATING"])
SH=int(os.environ["SHARD"]); NS=int(os.environ["NS"]); REC=38
_REC=struct.Struct("<QQQQBib")
log=logging.getLogger("mine"); log.addHandler(logging.NullHandler())
def pc(wm,wk,bm,bk): return bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
def val(men,king): return bin(men).count('1')+3*bin(king).count('1')
conn=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
cur=conn.execute("""SELECT id,pdn,result FROM expert_games
    WHERE result IN ('1-0','0-1') AND num_plies>=24
      AND (COALESCE(white_rating,0)>=? OR COALESCE(black_rating,0)>=?)
    ORDER BY id""",(MINR,MINR))
orc=JassOracle(JASS, log)
out=open(f"{DB}.fline.{SH}","wb"); kept=0; gi=-1; seen=set()
for row in cur:
    gi+=1
    if gi>=MAXG: break
    if gi%NS!=SH: continue
    gid,pdn,result=row[0],row[1],row[2]
    moves=extract_moves(_strip_tags_and_comments(pdn or ""))
    if len(moves)<24: continue
    winner_white=(result=='1-0')
    try:
        orc.reset()
        pos=[]
        stm0,wm,wk,bm,bk=fen_to_bitboards(orc.fen()); pos.append((wm,wk,bm,bk,stm0))
        okg=True
        for mv in moves:
            if not orc.apply(mv): okg=False; break
            stm,wm,wk,bm,bk=fen_to_bitboards(orc.fen()); pos.append((wm,wk,bm,bk,stm))
        if not okg or len(pos)<WIN+4: continue
    except Exception:
        continue
    def B(k):
        wm,wk,bm,bk,_=pos[k]; vw=val(wm,wk); vb=val(bm,bk)
        return (vw-vb) if winner_white else (vb-vw)
    Bk=[B(k) for k in range(len(pos))]
    gk=0
    for t in range(8, len(pos)-2):
        if gk>=CAP: break
        wm,wk,bm,bk,stm=pos[t]
        if not ((stm==0)==winner_white): continue        # racine = gagnant au trait
        p=pc(wm,wk,bm,bk)
        if not (LO<=p<=HI): continue
        base=Bk[t]; end=min(t+WIN,len(pos)-1); seg=Bk[t:end+1]
        dmin=min(seg); di=t+seg.index(dmin)
        if dmin > base-SAC: continue                      # VRAI sacrifice (a donne >= SAC)
        post=Bk[di:end+1]; gain=max(post)
        if gain < base+NET: continue                      # regain NET >= NET apres le sac
        res_idx=di+post.index(gain)                       # point de resolution (balance max post-sac)
        emitted=False
        for q in range(t,res_idx+1):                      # TOUTE la ligne : racine + noeuds materiel-en-bas + resolution
            wq,wkq,bq,bkq,sq=pos[q]; keyq=(wq,wkq,bq,bkq,sq)
            if keyq in seen: continue
            seen.add(keyq)
            wdl=1 if ((sq==0)==winner_white) else -1      # label = RESULTAT REEL, POV du trait
            out.write(_REC.pack(wq,wkq,bq,bkq,sq,0,wdl)); kept+=1; emitted=True
        if emitted: gk+=1
orc.close(); out.close()
print(f"shard {SH}: kept {kept}")
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/m.$s.log" 2>&1 & done; wait
cat "$W"/m.*.log | sed 's/^/  /' | tee -a "$RES"
# merge unique (x1)
python3 - "$W/fline_uniq.jnnw" "$DB.fline" "$NCPU" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); body=bytearray(); tot=0
for s in range(k):
    try: b=open(f"{pre}.{s}",'rb').read()
    except FileNotFoundError: continue
    n=(len(b)-8)//REC; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  positions full-line uniques={tot}")
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$DB.fline.$s"; done
NU=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/fline_uniq.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${NU:-0}" -ge 200 ] || { say "ABORT: mining quasi vide (${NU})."; exit 7; }
# replique pour atteindre ~TARGET_FRAC% du corpus (pool+egdb+combos)
REP=$(python3 -c "p=$NPOOL+$NEGDB; f=$TARGET_FRAC/100.0; tgt=f/(1-f)*p; import math; print(max(1,math.ceil(tgt/$NU)))")
python3 - "$W/fline_uniq.jnnw" "$W/fline.jnnw" "$REP" <<'PY'
import struct,sys; REC=38
src,dst,k=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',n*k)+body*k); print(n*k)
PY
cp "$W/fline_uniq.jnnw" "$ART/fline_uniq.jnnw" 2>/dev/null || true
# echantillon FEN pour audit
python3 - "$W/fline_uniq.jnnw" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
sl=lambda x:[i+1 for i in range(50) if (x>>i)&1]
print("  echantillon (noeuds de ligne forcante ; wdl = POV trait) :"); shown=0
for i in range(0,n,max(1,n//6)):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]; wdl=struct.unpack('<b',body[i*REC+37:i*REC+38])[0]
    f=f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}"
    print(f"    wdl={wdl:+d}  {f}"); shown+=1
    if shown>=5: break
PY

say "=== fit : pool + egdb-finale + flux FULL-LINE (poids LOURD ~${TARGET_FRAC}%) ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8010 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/fline.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])")
NFL=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/fline.jnnw','rb').read(8)[4:8])[0])")
say "  corpus final : ${NMIX}  (full-line ${NFL} = $((100*NFL/NMIX))% du corpus ; uniques=${NU}, replique x${REP})"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_fline.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_fline.pjtw" > "$ART/champion-fullline.pjtw.gz"; rm -f "$W/feat"
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
say ""; say "=== GATE 0440 : full-line vs Scan (DILF complet, d${D}, 1 seul juge => pas de troncature) ==="
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_fline.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-fullline" >"$W/cf.log" 2>&1 || say "  (conv fullline echoue)"
  say "  conversion 0440 : FULL-LINE(~${TARGET_FRAC}%) $(conv "$ART/conv-fullline")   [points etablis : egdbmix=0.302 ; 0464 racine 5.4%=0.304 ; 0466 racine 35%=0.308 ; Scan=0.95]"
  # bootstrap IC95 sur les parties-attaquant (resolution du juge a 305 positions, SE~0.026)
  python3 - "$ART/conv-fullline" "$DILF" <<'PY' | tee -a "$RES"
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
    import statistics
    m=sum(aw)/n
    # bootstrap deterministe (LCG, pas de Random non-seedable) : 2000 reechantillons
    seed=12345; boots=[]
    for _ in range(2000):
        acc=0
        for _ in range(n):
            seed=(1103515245*seed+12345)&0x7fffffff
            acc+=aw[seed%n]
        boots.append(acc/n)
    boots.sort(); lo=boots[int(0.025*len(boots))]; hi=boots[int(0.975*len(boots))]
    print(f"  IC95 (bootstrap, n={n}) : {m:.3f}  [{lo:.3f} , {hi:.3f}]   (egdbmix 0.302 DANS l'IC => statistiquement plat)")
else: print("  IC95 : pas de parties-attaquant")
PY
else say "  GATE 0440 : Scan absent => champion committe ; conversion 0440 a faire avec Scan."; fi
say ""; say "================= LECTURE ================="
say "  FULL-LINE >> 0.31 => on supervisait les MAUVAISES positions (racine seule) : enseigner la ligne (voir au-dela du sac)"
say "       debloque la conversion => le levier tactique externe VIT => scaler. C2-(2) ROUVERT."
say "  FULL-LINE ~ 0.31  => 5e echec d'affilee, MECANISME tactique epuise (racine ET ligne, auto ET externe, dilue ET lourd)"
say "       => la classe lineaire ne represente PAS le signal combinatoire a geometrie verrouillee => PLAFOND FEATURE solide."
say "       => avec 0461(FIT) + 0465(donnees-mu) + DRAWISH, C2 vide => C3/C4 du gate NNUE deviennent decisifs."
say "=========================================="
