#!/usr/bin/env bash
# id: ccx33-0464-master-combo-mining
# description: SUPERVISION TACTIQUE v3 — VERITE EXTERNE (le seul levier restant apres l'echec des deux supervisions AUTO).
# 0462 a mine des positions de milieu et les a labelisees avec la recherche d6-elagage-OFF de JASS LUI-MEME => 0.285 sur 0440
# (echec) : on ne peut pas enseigner a jass les combinaisons qu'il NE VOIT PAS avec des labels produits par son propre oeil
# (auto-supervision bornee par la vue propre, cf aussi 0460 0.259). Ici la SEULE difference avec 0462 : le flux tactique vient
# de VRAIES PARTIES (expert_games.db, box-local, parties lidraughts decisives) ou une COMBINAISON a ete JOUEE par un humain
# (vue externe, au-dela des angles morts de jass) ; on la detecte par le PROFIL MATERIEL DE LA LIGNE REELLE (sacrifice ->
# regain net >=2 pions dans la fenetre, gagnant au trait) et on labelise par le RESULTAT REEL de la partie (wdl=+1 cote
# gagnant). AUCUN moteur dans le label => ni auto-supervision ni distillation Scan : pure verite-terrain. Meme base que 0462
# (pool+egdb), meme fit, meme juge 0440 => A/B propre "vue propre (0462=0.285) vs vue externe". Pilote/leaf = egdbmix. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0464-master-combo-mining/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mcombo; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
DILF=data/dilf_combinations.fen
DB=/root/jass/data/expert_games.db
GEOM32=/root/jass-geom32-mcombo
POOL_TRIM=18000000; NEGDB=4000000; MID_LO=12; MID_HI=44; OVERSAMPLE=8
WINDOW=12; NET_MIN=2; SAC_MIN=1; CAP_PER_GAME=8; MAX_GAMES=200000; MIN_RATING=1600
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11; JUDGE_PAIRS=28
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire ailleurs)"
[ -f "$DB" ] || { say "ABORT: expert_games.db absent ($DB) — la DB box-local de 0438 n'a pas survecu ; relancer ccx33-0438 d'abord."; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
NG=$(python3 -c "import sqlite3;print(sqlite3.connect('file:$DB?mode=ro',uri=True).execute(\"select count(*) from expert_games where result in ('1-0','0-1')\").fetchone()[0])" 2>/dev/null || echo 0)
say "  DB : ${NG} parties decisives (result 1-0/0-1)"
[ "${NG:-0}" -ge 2000 ] || { say "ABORT: trop peu de parties decisives (${NG}) pour miner des combinaisons."; exit 4; }
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

say "=== assemble pool self-play (meme base que 0462) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"

say "=== MINE combinaisons depuis les VRAIES parties (sacrifice -> regain net >=${NET_MIN}, gagnant au trait ; label = resultat reel) ==="
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
out=open(f"{DB}.combo.{SH}","wb"); kept=0; gi=-1; seen=set()
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
        pos=[]  # list of (wm,wk,bm,bk,stm)
        stm0,wm,wk,bm,bk=fen_to_bitboards(orc.fen()); pos.append((wm,wk,bm,bk,stm0))
        okg=True
        for mv in moves:
            if not orc.apply(mv): okg=False; break
            stm,wm,wk,bm,bk=fen_to_bitboards(orc.fen()); pos.append((wm,wk,bm,bk,stm))
        if not okg or len(pos)<WIN+4: continue
    except Exception:
        continue
    # balance B[k] = val(winner) - val(loser) at position k ; winner material from absolute bitboards
    def B(k):
        wm,wk,bm,bk,_=pos[k]
        vw=val(wm,wk); vb=val(bm,bk)
        return (vw-vb) if winner_white else (vb-vw)
    Bk=[B(k) for k in range(len(pos))]
    gk=0
    for t in range(8, len(pos)-2):
        if gk>=CAP: break
        wm,wk,bm,bk,stm=pos[t]
        winner_to_move=((stm==0)==winner_white)
        if not winner_to_move: continue
        p=pc(wm,wk,bm,bk)
        if not (LO<=p<=HI): continue
        base=Bk[t]
        end=min(t+WIN,len(pos)-1)
        seg=Bk[t:end+1]
        dmin=min(seg); di=t+seg.index(dmin)
        if dmin > base-SAC: continue                 # exige un VRAI sacrifice (a donne >= SAC)
        post=Bk[di:end+1]
        if max(post) < base+NET: continue            # et un regain NET >= NET apres le sacrifice
        key=(wm,wk,bm,bk,stm)
        if key in seen: continue
        seen.add(key)
        out.write(_REC.pack(wm,wk,bm,bk,stm,0,1))    # wdl=+1 (STM = gagnant = a la combinaison)
        kept+=1; gk+=1
orc.close(); out.close()
print(f"shard {SH}: kept {kept}")
PY
}
export -f worker
for s in $(seq 0 $((NCPU-1))); do worker "$s" "$NCPU" >"$W/m.$s.log" 2>&1 & done; wait
cat "$W"/m.*.log | sed 's/^/  /' | tee -a "$RES"
python3 - "$W/combos.jnnw" "$DB.combo" "$NCPU" "$OVERSAMPLE" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); ov=int(sys.argv[4]); body=bytearray(); base=0
for s in range(k):
    try: b=open(f"{pre}.{s}",'rb').read()
    except FileNotFoundError: continue
    base+=len(b)//REC
    for _ in range(ov): body+=b
tot=len(body)//REC
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body))
print(f"  combinaisons uniques={base} ; flux tactique externe (oversample x{ov})={tot}")
PY
for s in $(seq 0 $((NCPU-1))); do rm -f "$DB.combo.$s"; done
NC=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
# dump quelques FEN pour audit visuel
python3 - "$W/combos.jnnw" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
sl=lambda x:[i+1 for i in range(50) if (x>>i)&1]
print("  echantillon (positions a combinaison, gagnant au trait) :")
seen=set()
for i in range(0,n, max(1,n//6)):
    wm,wk,bm,bk=struct.unpack('<QQQQ',body[i*REC:i*REC+32]); stm=body[i*REC+32]
    f=f"{'W' if stm==0 else 'B'}:W{','.join([str(s) for s in sl(wm)]+['K'+str(s) for s in sl(wk)])}:B{','.join([str(s) for s in sl(bm)]+['K'+str(s) for s in sl(bk)])}"
    if f in seen: continue
    seen.add(f); print("   ",f)
    if len(seen)>=5: break
PY
cp "$W/combos.jnnw" "$ART/combos.jnnw" 2>/dev/null || true
[ "${NC:-0}" -ge 1000 ] || { say "  (trop peu de combinaisons: ${NC} — baisser NET_MIN/SAC_MIN ou MAX_GAMES plus haut). On continue quand meme si >=200."; }
[ "${NC:-0}" -ge 200 ] || { say "ABORT: mining quasi vide (${NC}) — la DB ou le detecteur ne donnent rien d'exploitable."; exit 7; }

say "=== fit : pool + egdb-finale + flux COMBINAISONS-VERITE sur-pondere ==="
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8008 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/combos.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])"); say "  corpus final : ${NMIX}"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_combo.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_combo.pjtw" > "$ART/champion-mastercombo.pjtw.gz"; rm -f "$W/feat"
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
say "  self-direct : mastercombo vs egdbmix = $(pjudge "$W/champ_combo.pjtw" "$W/pilot.pjtw")"
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/pilot.pjtw"      --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-egdbmix" >"$W/ce.log" 2>&1 || say "  (conv egdbmix echoue)"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_combo.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-combo"   >"$W/cc.log" 2>&1 || say "  (conv combo echoue)"
  say "  conversion 0440 : egdbmix $(conv "$ART/conv-egdbmix")   MASTERCOMBO $(conv "$ART/conv-combo")   (rappel : egdbmix~0.302 ; 0462 shotfilter AUTO=0.285 ; Scan 0.95)"
else say "  GATE 0440 : Scan absent => champion committe ; conversion 0440 a faire avec Scan."; fi
say ""; say "================= LECTURE ================="
say "  MASTERCOMBO > egdbmix (0.302) ET > 0462-AUTO (0.285) => la VERITE EXTERNE deplace 0440 la ou l'auto-supervision echouait"
say "      => le levier est bien la VUE EXTERNE (parties de maitres), pas le volume auto-genere. Promouvoir + scaler le mining."
say "  MASTERCOMBO ~ 0462 ~ egdbmix => meme la verite-terrain tactique externe ne bouge pas 0440 a features verrouillees"
say "      => indice fort de PLAFOND FEATURE lineaire (cf 0461 FIT-pas-FEATURE a l'envers) => rouvrir le debat du gate NNUE (C3/C4)."
say "=========================================="
