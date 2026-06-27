#!/usr/bin/env bash
# id: ccx33-0482-fromscratch-material-seed
# description: BRAS "SEED MATERIEL PUR" du bootstrap from-scratch (go JFC 2026-06-27) — croise 0481 (seed eval-defaut sur
# cpx62). MEME protocole, MEME volume, MEME depth, MEME elagage : la SEULE difference est le seed de la generation 1.
# 0481 part de l'eval embarquee (materiel + king-PST + mob + balance) = un primitif APPRIS, ancetre lointain de la lignee
# egdbmix -> objection possible "tu n'es pas VRAIMENT parti de zero, le seed porte deja le biais de la lignee". Ici on forge
# un seed MATERIEL PUR (men=1, roi=3, ZERO prior positionnel), totalement independant d'egdbmix (ne partage QUE les regles)
# -> equivalent litteral du seed "piece-count, roi=3 hommes" de Scan. Si LES DEUX bras (0481 eval-defaut + 0482 materiel-pur)
# convergent vers le meme plateau ~0.28, la preuve "plateau = propriete de la CLASSE, pas de l'init" est BLINDEE (deux seeds
# independants). S'ils divergent, c'est un signal de dependance au chemin a creuser.
#
# FORGE DU SEED MATERIEL (robuste, via le pipeline canonique — pas de binaire forge a la main) :
#   gen 1.5M positions diverses avec l'eval embarquee -> REETIQUETTE le wdl = signe(materiel STM-POV, men=1 roi=3)
#   -> dump-eval-features -> fit logistic -> seed-materiel.pjtw (= meilleure approx lineaire-en-patterns du materiel pur,
#   zero connaissance positionnelle/tactique au-dela du materiel). VERIFIE via --eval-position (blanc +1 homme => eval>0 ;
#   noir -1 homme => eval<0) ; ABORT si degenere. C'est l'eval qui PILOTE la generation 1 du bootstrap.
#
# PROTOCOLE bootstrap (identique a 0481) :
#   gen 1  : self-play pilote par seed-materiel.pjtw -> fit -> champ-gen1.
#   gen k>1: self-play FRAIS pilote par champ-gen(k-1) (CHAINE FORCEE) -> fit -> champ-gen k.
# Juge 0440 vs Scan (depth-fixe 11, no-DB, 305 combos dilf) + IC95 a chaque generation + vs_egdbmix + vs_prev. Courbe
# committee gen-par-gen (curve.txt + champion-gen$k.pjtw.gz + conv-gen$k/). Volume CONSTANT 10M/gen. Reprise-safe.
# 100% LINEAIRE. AUCUN NNUE. AUCUNE distillation Scan (labels self-play jass + materiel pour le seed ; PAS de Scan, PAS de
# gen-egdb-wld). egdb seulement pour la resolution correcte des finales en self-play.
set -uo pipefail
cd /root/jass
# ----- params (IDENTIQUES a 0481 sauf le seed) -----
KGEN=10
FRESH=10000000
PLAY_DEPTH=10
LABEL_DEPTH=4
OPEN_PLIES=8
EXPLORE_EPS=5
MID_LO=14; MID_HI=40; SEED_CAP=400000; SEED_FRAC=25
JUDGE_PAIRS=28
D=11
CHUNK=1000000; MAXIT=25; L2=3e-5
SEED_CORPUS=1500000            # corpus jetable pour FORGER le seed materiel (gen eval-defaut -> reetiquette materiel -> fit)
SEED_CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF_FEN=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
# ------------------
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-3000}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0482-fromscratch-material-seed/artefacts"; mkdir -p "$ART"
W=/root/cw-matseed; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-matseed
RES="$ART/RESULTS.txt"; CURVE="$ART/curve.txt"; TRAJ="$ART/trajectory.txt"
say(){ echo "$@" | tee -a "$RES"; }
[ -f "$RES" ] || : > "$RES"; [ -f "$CURVE" ] || : > "$CURVE"; [ -f "$TRAJ" ] || : > "$TRAJ"

preflight_build 1; preflight_train "$FRESH" "$KGEN"
preflight_note "from-scratch MATERIEL : forge seed + ${KGEN} generations chainees (gen ${FRESH} + refit + juge 0440)" 1800
preflight_check

# ---------- build 32-pat (memes flags que 0481) ----------
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -8 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — juge 0440 a refaire ailleurs)"

git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && git show "origin/main:$SEED_CH" | gunzip > "$W/egdbmix.pjtw" || { say "  (egdbmix absent — vs_base saute)"; : > "$W/egdbmix.pjtw"; }

# ---------- seed-files milieu (dilf + lidraughts) pour la diversite mu ----------
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W" "$DILF_FEN" "$MID_LO" "$MID_HI" "$SEED_CAP" $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; W=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xBEEF)
drecs=bytearray(); nd=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); drecs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); nd+=1
mids=[]
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; body=memoryview(raw)[8:8+m*REC]
    for i in range(m):
        r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: mids.append(bytes(r))
random.shuffle(mids); mids=mids[:cap]
both=bytearray(drecs)+bytearray().join(mids)
open(f"{W}/seeds_both.jnnw",'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(both))
print(f"  seeds milieu : dilf={nd} lidraughts={len(mids)} both={nd+len(mids)}")
PY
SEEDFILE="$W/seeds_both.jnnw"

# ---------- helpers (merge/gen/fit/juges) ----------
merge(){ python3 - "$1" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
rm -f "$1".[0-9]* ; }
gen2(){ local pilot="$1" nn="$2" out="$3"
  local per=$(( (nn+NCPU-1)/NCPU )); local nnopt=""
  [ "$pilot" != "DEFAULT" ] && nnopt="--nnue $pilot"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" \
      $nnopt --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" >/dev/null 2>&1 & done; wait
  merge "$out"; }
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $3"; tail -10 "${3%.pjtw}.log"|sed 's/^/  /'; exit 9; }; }
pjudge(){ [ -s "$2" ] || { echo "NA"; return; }
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" \
    --jass-b "$J" --pattern-b "$2" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
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
conv_ci(){ python3 - "$1" "$DILF_FEN" <<'PY'
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

# ---------- FORGE DU SEED MATERIEL PUR (men=1, roi=3, zero prior positionnel) ----------
SEED_MAT="$W/seed-materiel.pjtw"; SEED_GZ="$ART/seed-materiel.pjtw.gz"
if [ -f "$SEED_GZ" ]; then
  gunzip -c "$SEED_GZ" > "$SEED_MAT"; say "  (reprise) seed materiel restaure depuis l'artefact"
else
  say "=== forge seed materiel pur (gen ${SEED_CORPUS} eval-defaut -> reetiquette materiel -> fit) ==="
  gen2 "DEFAULT" "$SEED_CORPUS" "$W/matcorp.jnnw"
  # reetiquette le wdl (offset 37) = signe du materiel STM-POV (men=1, roi=3) ; stm a l'offset 32
  python3 - "$W/matcorp.jnnw" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
p=sys.argv[1]; raw=bytearray(open(p,'rb').read()); n=struct.unpack('<I',raw[4:8])[0]
pos=8; pos1=pos0=eq=0
for i in range(n):
    o=pos+i*REC
    wm,wk,bm,bk=struct.unpack('<QQQQ',raw[o:o+32]); stm=raw[o+32]
    mw=bin(wm).count('1')+3*bin(wk).count('1'); mb=bin(bm).count('1')+3*bin(bk).count('1')
    diff=(mw-mb) if stm==0 else (mb-mw)           # STM-POV
    w=1 if diff>0 else (-1 if diff<0 else 0)
    raw[o+37:o+38]=struct.pack('<b',w)
    pos1+=w>0; pos0+=w<0; eq+=w==0
open(p,'wb').write(raw)
print(f"  reetiquette materiel : n={n} (+={pos1} -={pos0} nul={eq})")
PY
  "$J" --dump-eval-features "$W/matcorp.jnnw" "$W/matfeat" >"$W/matfeat.log" 2>&1 || { say "ABORT dump feat seed"; exit 8; }
  fit "$W/matcorp.jnnw" "$W/matfeat" "$SEED_MAT"
  rm -f "$W/matfeat" "$W/matcorp.jnnw"
  # VERIFICATION : blanc +1 homme => eval STM-POV > 0 ; noir -1 homme => eval STM-POV < 0
  EW=$("$J" --eval-position "$SEED_MAT" "W:W31,32,33:B18,19" 2>/dev/null | tr -dc '0-9-')
  EB=$("$J" --eval-position "$SEED_MAT" "B:W31,32,33:B18,19" 2>/dev/null | tr -dc '0-9-')
  say "  verif seed : eval(blanc-au-trait,+1h)=${EW}cp  eval(noir-au-trait,-1h)=${EB}cp  (attendu >0 et <0)"
  # gate sur le SIGNE (robuste a l'echelle absolue de l'eval) : +1 homme au trait => >0 ; -1 homme au trait => <0.
  # tout-zero (degenere) echoue EW>0. Ecart EW-EB doit etre franchement positif (le materiel est bien le signal dominant).
  awk "BEGIN{exit !(${EW:-0}+0 > 0 && ${EB:-0}+0 < 0 && (${EW:-0}-(${EB:-0})) >= 10)}" || { say "ABORT: seed materiel degenere (signe materiel non capte)"; exit 9; }
  gzip -c "$SEED_MAT" > "$SEED_GZ"
  say "  seed materiel forge + verifie OK -> pilote de la generation 1"
fi

# ---------- la boucle bootstrap : seed MATERIEL PUR -> chaine forcee ----------
grep -q "^gen 0" "$CURVE" 2>/dev/null || say "gen 0  seed=materiel-pur(men=1,roi=3,zero-positionnel)  egdbmix-0440=0.302  plateau-11-leviers~0.28  (croise 0481 seed eval-defaut)" | tee -a "$CURVE" >/dev/null
PILOT="$SEED_MAT"
for k in $(seq 1 "$KGEN"); do
  CHGZ="$ART/champion-gen$k.pjtw.gz"
  if [ -f "$CHGZ" ]; then
    gunzip -c "$CHGZ" > "$W/champ$k.pjtw"; PILOT="$W/champ$k.pjtw"
    say "  (reprise) generation $k deja committee -> pilote restaure, saute"
    continue
  fi
  PILNAME=$([ "$PILOT" = "$SEED_MAT" ] && echo "seed-materiel-pur(SEED)" || echo "champ-gen$((k-1))")
  say ""; say "================= GENERATION $k / $KGEN  (pilote = $PILNAME) ================="
  rm -f "$W/corpus.jnnw"
  gen2 "$PILOT" "$FRESH" "$W/corpus.jnnw"
  NTOT=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
  [ "${NTOT:-0}" -ge 1000000 ] || { say "  ABORT gen $k : corpus vide ($NTOT)"; exit 7; }
  "$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat-g$k.log" 2>&1 || { say "ABORT dump feat g$k"; exit 8; }
  fit "$W/corpus.jnnw" "$W/feat" "$W/champ$k.pjtw"
  rm -f "$W/feat" "$W/corpus.jnnw"
  gzip -c "$W/champ$k.pjtw" > "$CHGZ"
  VB=$(pjudge "$W/champ$k.pjtw" "$W/egdbmix.pjtw")
  VP="NA"; [ "$PILOT" != "$SEED_MAT" ] && VP=$(pjudge "$W/champ$k.pjtw" "$PILOT")
  if [ "$HAVE_SCAN" = 1 ]; then
    ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ$k.pjtw" \
        --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF_FEN" --dump-games-dir "$ART/conv-gen$k" >"$W/cv$k.log" 2>&1 ) || say "  (juge 0440 g$k echoue)"
    read M LO HI N < <(conv_ci "$ART/conv-gen$k")
    say "gen $k  0440=$M  IC95=[$LO,$HI]  (n=$N)  vs_egdbmix=$VB  vs_prev=$VP  pilote=$PILNAME" | tee -a "$CURVE"
  else
    say "gen $k  (Scan absent)  vs_egdbmix=$VB  vs_prev=$VP  pilote=$PILNAME" | tee -a "$CURVE"
  fi
  echo "gen $k  0440=${M:-NA} vs_egdbmix=$VB vs_prev=$VP" >> "$TRAJ"; cp "$TRAJ" "$ART/trajectory.txt"
  PILOT="$W/champ$k.pjtw"
done

say ""; say "================= COURBE BOOTSTRAP SEED-MATERIEL (croise 0481) ================="
cat "$CURVE" | sed 's/^/  /' | tee -a "$RES"
say ""; say "  LECTURE (a confronter a 0481) :"
say "   les DEUX bras (eval-defaut 0481 + materiel-pur 0482) collent a ~0.28 => plateau = CLASSE, preuve BLINDEE => gate NNUE."
say "   un bras MONTE et pas l'autre => dependance au seed/chemin => le point fixe est deplacable => creuser ce bras."
say "==========================================="
