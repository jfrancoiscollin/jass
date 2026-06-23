#!/usr/bin/env bash
# id: cpx62-0442-freshmix-loop
# description: NOUVELLE STRATEGIE self-play (demande JFC) : (1) 100% EPURE a chaque boucle — AUCUNE reutilisation, AUCUNE
# fenetre glissante : chaque boucle regenere un corpus ENTIEREMENT NEUF et fit dessus seul ; (2) un MIX DIFFERENT a
# chaque boucle pour faire bouger mu, en composant TOUS les leviers identifies : profondeur de JEU (blend d8/d10/d12),
# SEEDING hors-ouverture (milieux lidraughts + combinaisons dilf, seed_frac variable), plies d'ouverture aleatoires
# (--random-open-plies), EXPLORATION epsilon-random (--explore-eps), profondeur de LABEL. Pilote = meilleur champion
# jusqu'ici (montee gloutonne, depart = champion 3e-5). On JUGE chaque champion vs la BASE (3e-5, point fixe self-play
# connu) ET vs prev : la recette dont le champion bat le plus la base = la composition de mu gagnante. AUCUN NNUE, AUCUNE
# distillation Scan (regles gravees). Corpus frais box-local (regenerable) ; seuls champions + trajectoire committes.
set -uo pipefail
cd /root/jass
# ----- params -----
FRESH=12000000               # positions FRAICHES par boucle (100% neuf ; >saturation couverture ~10M pour un fit net)
LABEL_LO=4                   # label/score depth de base (le WDL vient du DEROULE a play-depth, pas de ce search)
JUDGE_PAIRS=28; PLAY_FALLBACK=10
MID_LO=14; MID_HI=40; SEED_CAP=400000
SEED_CH=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF_FEN=data/dilf_combinations.fen
CHUNK=1000000; MAXIT=25
# ----- RECETTES (une par boucle ; mix distinct) : play1 f1% play2 labeldepth seedset seedfrac openplies eps  nom -----
#   play = blend f1% @play1 + reste @play2 ; seedset in {lidr,dilf,both} ; toutes differentes
R_PLAY1=(10 10 10  8 12)
R_F1=(   70 100 50 60 100)
R_PLAY2=(12 10 12 10 12)
R_LABEL=( 4  4  6  4  6)
R_SEEDSET=(lidr both dilf lidr both)
R_SEEDFRAC=(30 20 40 25 30)
R_OPEN=(  6 14  8 10  6)
R_EPS=(   0 12  5  8  0)
R_NAME=(humain-profond exploration-large tactique volume-decisif haute-fidelite)
NREC=${#R_NAME[@]}
# ------------------
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-1500}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0442-freshmix-loop/artefacts"; mkdir -p "$ART"
W=/root/cw-freshmix; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-freshmix; TRAJ="$ART/trajectory.txt"; : > "$TRAJ"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }

preflight_build 1; preflight_train "$FRESH" "$NREC"; preflight_note "freshmix : ${NREC} boucles 100% epure (gen ${FRESH} mixe + refit + 2 juges)" 600; preflight_check

# ---------- build 32-pat (memes flags que 0428) + seed champion ----------
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb"; exit 6; }
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -8 "$W/build.log"; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git cat-file -e "origin/main:$SEED_CH" 2>/dev/null || { say "ABORT: graine $SEED_CH absente"; exit 4; }
git show "origin/main:$SEED_CH" | gunzip > "$W/champ0.pjtw"

# ---------- seed-files : dilf, lidraughts(milieux), both ----------
say "=== seed-files (dilf combinaisons / lidraughts milieux / both) ==="
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
[ -n "$SHARDS" ] && say "  shards lidraughts : $(echo "$SHARDS"|wc -l)" || say "  (shards lidraughts ABSENTS — seeds lidr/both = dilf seul)"
python3 - "$W" "$DILF_FEN" "$MID_LO" "$MID_HI" "$SEED_CAP" $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; W=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xBEEF)
def write(path,recs,n): open(path,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs))
drecs=bytearray(); nd=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b); drecs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); nd+=1
write(f"{W}/seeds_dilf.jnnw",drecs,nd)
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
lrecs=bytearray().join(mids) if mids else drecs  # fallback: dilf si pas de lidraughts
write(f"{W}/seeds_lidr.jnnw",lrecs,len(mids) if mids else nd)
both=bytearray(drecs)+bytearray().join(mids); write(f"{W}/seeds_both.jnnw",both,nd+len(mids))
print(f"  dilf={nd}  lidraughts_milieu={len(mids)}  both={nd+len(mids)}")
PY
seedfile_for(){ case "$1" in lidr) echo "$W/seeds_lidr.jnnw";; dilf) echo "$W/seeds_dilf.jnnw";; *) echo "$W/seeds_both.jnnw";; esac; }

# ---------- helpers ----------
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
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
gen2(){ local pilot="$1" nn="$2" out="$3" pdepth="$4" ldepth="$5" sf="$6" open="$7" eps="$8" seedfile="$9"
  [ "$nn" -le 0 ] && { : > "$out"; return; }
  local per=$(( (nn+NCPU-1)/NCPU )); local sa=""
  [ -n "$seedfile" ] && [ "${sf:-0}" -gt 0 ] && sa="--seed-file $seedfile --seed-frac $sf"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$ldepth" "$pdepth" 200 "$((RANDOM*RANDOM+s))" \
      --nnue "$pilot" --random-open-plies "$open" --explore-eps "$eps" $sa >/dev/null 2>&1 & done; wait
  merge "$out"; }
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 3e-5 --max-iter "$MAXIT" --chunk "$CHUNK" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $3"; tail -10 "${3%.pjtw}.log"; exit 9; }; }
pjudge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" \
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

# ---------- la boucle : 100% epure + recette distincte par boucle ----------
BEST_CH="$W/champ0.pjtw"; BEST_VB="0.5000"; BEST_NAME="base-3e-5"
say "iter 0  base=champion-3e-5  (NREC=${NREC} recettes, FRESH=${FRESH}/boucle, 100% epure)" | tee -a "$TRAJ"
for k in $(seq 1 "$NREC"); do
  idx=$((k-1)); p1=${R_PLAY1[$idx]}; f1=${R_F1[$idx]}; p2=${R_PLAY2[$idx]}; ld=${R_LABEL[$idx]}
  ss=${R_SEEDSET[$idx]}; sf=${R_SEEDFRAC[$idx]}; op=${R_OPEN[$idx]}; ep=${R_EPS[$idx]}; nm=${R_NAME[$idx]}
  SF_FILE=$(seedfile_for "$ss")
  n1=$(( FRESH*f1/100 )); n2=$(( FRESH-n1 ))
  say "=== BOUCLE $k [$nm] : ${f1}% d${p1} + $((100-f1))% d${p2} | label d${ld} | seeds=${ss} frac=${sf}% | open=${op} eps=${ep}% | pilote=${BEST_NAME} ==="
  rm -f "$W/corpus.jnnw"
  gen2 "$BEST_CH" "$n1" "$W/c1.jnnw" "$p1" "$ld" "$sf" "$op" "$ep" "$SF_FILE"; app "$W/c1.jnnw" "$W/corpus.jnnw" >/dev/null
  gen2 "$BEST_CH" "$n2" "$W/c2.jnnw" "$p2" "$ld" "$sf" "$op" "$ep" "$SF_FILE"; [ "$n2" -gt 0 ] && app "$W/c2.jnnw" "$W/corpus.jnnw" >/dev/null
  NTOT=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])")
  "$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat-k$k.log" 2>&1 || { say "ABORT dump feat k$k"; exit 8; }
  fit "$W/corpus.jnnw" "$W/feat" "$W/champ$k.pjtw"
  gzip -c "$W/champ$k.pjtw" > "$ART/champion-${k}-${nm}.pjtw.gz"
  VB=$(pjudge "$W/champ$k.pjtw" "$W/champ0.pjtw")        # vs BASE (3e-5)
  VP=$(pjudge "$W/champ$k.pjtw" "$BEST_CH")              # vs pilote courant (meilleur jusqu'ici)
  adopt=""
  awk "BEGIN{exit !(${VB}+0 > ${BEST_VB}+0)}" && { BEST_CH="$W/champ$k.pjtw"; BEST_VB="$VB"; BEST_NAME="$nm"; adopt=" <- NOUVEAU MEILLEUR (adopte comme pilote)"; }
  say "  BOUCLE $k [$nm] : corpus=${NTOT}  vs_BASE=${VB}  vs_pilote=${VP}${adopt}"
  echo "iter $k  recette=${nm}  vs_base=${VB}  vs_pilote=${VP}  corpus=${NTOT}${adopt}" | tee -a "$TRAJ" >/dev/null
  cp "$TRAJ" "$ART/trajectory.txt"
  echo "iter $k  recette=${nm}  vs_base=${VB}  vs_pilote=${VP}${adopt}" > "$ART/iter${k}-score.txt"
done

# meilleur champion durable
gzip -c "$BEST_CH" > "$ART/champion-freshmix-best.pjtw.gz" 2>/dev/null || true
say ""
say "================= LECTURE ================="
say "  Meilleure recette = ${BEST_NAME} (vs_base=${BEST_VB})."
say "  vs_base > 0.55 pour une recette => sa composition de mu a CASSE le point fixe self-play (sans NNUE/distillation)."
say "  => prochaine etape : juger ce champion vs SCAN (ccx33), et re-tirer une 2e generation de recettes autour de la gagnante."
say "  vs_base ~ 0.50 partout => aucune composition testee ne deplace assez mu => indice features/capacite (a discuter)."
say "==========================================="
