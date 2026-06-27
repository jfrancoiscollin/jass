#!/usr/bin/env bash
# id: cpx62-0481-fromscratch-bootstrap
# description: LE DERNIER LEVIER LINEAIRE FIDELE A SCAN (go JFC 2026-06-27, apres ~11 leviers donnees/entrainement TOUS plats
# a ~0.28 sur 0440 : 0460..0479). Recherche clean-room => Scan a ete monte DEPUIS ZERO en self-play pur (seed = eval
# materielle primitive + regles, PAS de prof, PAS de master-games), logistic regression ITEREE sur des centaines de
# generations. Nous, a CHAQUE essai precedent, on a pilote le gen depuis egdbmix — un point fixe DEJA forme, possiblement
# COINCE — et on a fait varier mu/volume/elagage AUTOUR de ce meme point fixe. On n'a JAMAIS refait la recette Scan :
# repartir d'un seed primitif et ITERER le bootstrap longtemps pour laisser le point fixe MIGRER. C'est le seul trou
# restant dans la preuve "le lineaire est epuise".
#
# PROTOCOLE (bootstrap force, PAS de montee gloutonne — on observe la TRAJECTOIRE, pas un hill-climb sur une metrique
# possiblement fausse, cf l'erreur 0465 qui grimpait sur vs_base) :
#   gen 1  : self-play pilote par l'EVAL EMBARQUEE PAR DEFAUT (jass SANS --nnue = eval "Cycle 8/pre-v5" : materiel +
#            king-PST + mobilite + balance — l'equivalent jass du seed "piece-count, roi=3 hommes" de Scan, et surtout
#            TRES loin du point fixe egdbmix). -> fit logistic -> champ-gen1.
#   gen k>1: self-play FRAIS pilote par champ-gen(k-1) (CHAINE FORCEE) -> fit -> champ-gen k.
# A chaque generation : juge 0440 vs Scan (depth-fixe 11, eval pure no-DB, 305 combinaisons dilf) + IC95 bootstrap, plus
# vs_egdbmix (ancre : le point fixe coince) et vs_prev (a-t-on bouge ?). La COURBE {0440_g1..gK} est committee
# (curve.txt + champion-gen$k.pjtw.gz + conv-gen$k/, survit au non-flush). Volume CONSTANT 10M/gen (>= saturation ~10M
# par TVR => le point fixe mesure est celui de l'EVAL, pas un artefact d'echantillon ; tue d'avance l'objection
# volume-confound de 0466/0467). Reprise-safe : une generation deja committee (champion-gen$k.pjtw.gz) est restauree et
# sautee (survit aux resets de conteneur).
#
# LECTURE (le decideur) :
#   courbe MONTE generation apres generation vers >=0.50 puis au-dela de 0.28 => l'init comptait, egdbmix etait un point
#       fixe coince, le lineaire N'EST PAS epuise => continuer le bootstrap (refit la gagnante a plein volume).
#   courbe revient se COLLER a ~0.28 (le meme plateau qu'egdbmix) malgre un seed totalement different => le plateau est
#       une propriete de la CLASSE lineaire + nos features, PAS de l'initialisation => le lineaire est PROUVE epuise =>
#       la gate NNUE s'ouvre proprement, preuve a l'appui (11 leviers + le bootstrap from-scratch).
# 100% LINEAIRE. AUCUN NNUE. AUCUNE distillation Scan (labels = resultats de self-play jass uniquement, PAS de
# gen-egdb-wld, PAS de Scan dans le label). egdb dispo seulement pour la RESOLUTION CORRECTE des finales en self-play
# (equivalent a jouer la partie jusqu'au bout avec les regles roi=3h — pas une distillation de verite externe).
set -uo pipefail
cd /root/jass
# ----- params -----
KGEN=10                        # generations de bootstrap (assez pour voir monter-vs-plateau ; chaque gen committee)
FRESH=10000000                 # positions FRAICHES/generation. 10M = a la saturation TVR (le point fixe mesure = celui de l'eval)
PLAY_DEPTH=10                  # profondeur de JEU du self-play (le WDL vient du deroule a cette profondeur)
LABEL_DEPTH=4                  # profondeur du score de label (le signal WDL vient du resultat, pas de ce search)
OPEN_PLIES=8                   # plies d'ouverture aleatoires (diversite mu, comme 0465)
EXPLORE_EPS=5                  # exploration epsilon % (diversite mu)
MID_LO=14; MID_HI=40; SEED_CAP=400000; SEED_FRAC=25   # seeds milieu (dilf+lidraughts) pour la diversite, frac constante
JUDGE_PAIRS=28                 # juges internes vs_egdbmix / vs_prev
D=11                           # 0440 : depth-fixe 11, eval pure no-DB (la jauge tactique du programme)
CHUNK=1000000; MAXIT=25; L2=3e-5
SEED_CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz   # ancre vs_base (le point fixe coince)
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF_FEN=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
# ------------------
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-3000}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0481-fromscratch-bootstrap/artefacts"; mkdir -p "$ART"
W=/root/cw-fromscratch; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-fromscratch
RES="$ART/RESULTS.txt"; CURVE="$ART/curve.txt"; TRAJ="$ART/trajectory.txt"
say(){ echo "$@" | tee -a "$RES"; }
[ -f "$RES" ] || : > "$RES"; [ -f "$CURVE" ] || : > "$CURVE"; [ -f "$TRAJ" ] || : > "$TRAJ"

preflight_build 1; preflight_train "$FRESH" "$KGEN"
preflight_note "from-scratch bootstrap : seed eval-defaut -> ${KGEN} generations chainees (gen ${FRESH} + refit + juge 0440)" 1800
preflight_check

# ---------- build 32-pat (memes flags que 0465/0474) ----------
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

# ancre vs_base = egdbmix (le point fixe coince qu'on cherche a quitter)
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
# gen self-play : pilot="DEFAULT" => SANS --nnue (eval embarquee = seed primitif from-scratch) ; sinon --nnue pilot
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

# ---------- la boucle bootstrap : seed primitif -> chaine forcee ----------
grep -q "^gen 0" "$CURVE" 2>/dev/null || say "gen 0  seed=eval-defaut(materiel+king-PST+mob+balance)  egdbmix-0440=0.302  plateau-11-leviers~0.28" | tee -a "$CURVE" >/dev/null
PILOT="DEFAULT"
for k in $(seq 1 "$KGEN"); do
  CHGZ="$ART/champion-gen$k.pjtw.gz"
  if [ -f "$CHGZ" ]; then                       # reprise : generation deja faite -> restaure le pilote, saute
    gunzip -c "$CHGZ" > "$W/champ$k.pjtw"; PILOT="$W/champ$k.pjtw"
    say "  (reprise) generation $k deja committee -> pilote restaure, saute"
    continue
  fi
  PILNAME=$([ "$PILOT" = "DEFAULT" ] && echo "eval-defaut(SEED)" || echo "champ-gen$((k-1))")
  say ""; say "================= GENERATION $k / $KGEN  (pilote = $PILNAME) ================="
  rm -f "$W/corpus.jnnw"
  gen2 "$PILOT" "$FRESH" "$W/corpus.jnnw"
  NTOT=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
  [ "${NTOT:-0}" -ge 1000000 ] || { say "  ABORT gen $k : corpus vide ($NTOT)"; exit 7; }
  "$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat-g$k.log" 2>&1 || { say "ABORT dump feat g$k"; exit 8; }
  fit "$W/corpus.jnnw" "$W/feat" "$W/champ$k.pjtw"
  rm -f "$W/feat" "$W/corpus.jnnw"
  gzip -c "$W/champ$k.pjtw" > "$CHGZ"
  # juges : 0440 vs Scan (la jauge) + vs_egdbmix (le point fixe coince) + vs_prev (a-t-on bouge ?)
  VB=$(pjudge "$W/champ$k.pjtw" "$W/egdbmix.pjtw")
  VP="NA"; [ "$PILOT" != "DEFAULT" ] && VP=$(pjudge "$W/champ$k.pjtw" "$PILOT")
  if [ "$HAVE_SCAN" = 1 ]; then
    ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ$k.pjtw" \
        --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF_FEN" --dump-games-dir "$ART/conv-gen$k" >"$W/cv$k.log" 2>&1 ) || say "  (juge 0440 g$k echoue)"
    read M LO HI N < <(conv_ci "$ART/conv-gen$k")
    say "gen $k  0440=$M  IC95=[$LO,$HI]  (n=$N)  vs_egdbmix=$VB  vs_prev=$VP  pilote=$PILNAME" | tee -a "$CURVE"
  else
    say "gen $k  (Scan absent)  vs_egdbmix=$VB  vs_prev=$VP  pilote=$PILNAME" | tee -a "$CURVE"
  fi
  echo "gen $k  0440=${M:-NA} vs_egdbmix=$VB vs_prev=$VP" >> "$TRAJ"; cp "$TRAJ" "$ART/trajectory.txt"
  PILOT="$W/champ$k.pjtw"        # CHAINE FORCEE : champ-gen k pilote la generation suivante (bootstrap)
done

say ""; say "================= COURBE BOOTSTRAP FROM-SCRATCH (le decideur) ================="
cat "$CURVE" | sed 's/^/  /' | tee -a "$RES"
say ""; say "  LECTURE :"
say "   0440 MONTE gen-apres-gen au-dela de 0.28 => l'init comptait, egdbmix etait coince, lineaire PAS epuise => continuer."
say "   0440 revient se coller a ~0.28 (= plateau egdbmix) malgre un seed tout autre => plateau = propriete de la CLASSE,"
say "        PAS de l'init => le lineaire est PROUVE epuise => la gate NNUE s'ouvre, preuve a l'appui (11 leviers + bootstrap)."
say "==========================================="
