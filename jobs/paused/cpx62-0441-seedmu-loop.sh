#!/usr/bin/env bash
# id: cpx62-0441-seedmu-loop
# description: FAIRE BOUGER mu (la distribution stationnaire qui fixe le point fixe lineaire). 0428 est a son point fixe
# (vs_prev=0.50) : iterer/regenerer avec un meilleur pilote ne bouge pas mu (verrou on-policy). LEVIER A = SEEDING
# hors-ouverture : on demarre seed_frac% des parties self-play depuis des positions de MILIEU humaines (lidraughts) +
# des COMBINAISONS (dilf), puis jass joue la suite a d10 => couverture d'etats NOUVELLE avec des labels VERIDIQUES (pas
# le resultat-partie bruite). Comme train_stream regresse sur le resultat MC (pas une valeur bootstrappee), elargir mu
# hors-politique est SANS risque de divergence. Boucle identique a 0428 mais --seed-frac 30 a chaque gen ; on JUGE chaque
# champion vs la BASE = champion 3e-5 (le point fixe self-play connu) : s'il grimpe > 0.55 vs base => mu a bouge, point
# fixe casse. CONTROLE D = re-ponderer le pool self-play PUR (sur-echantillonne le milieu, AUCUNE data nouvelle) -> fit
# -> juge vs base : isole la part du gain qui vient de la simple re-ponderation vs de la nouvelle couverture. AUCUN NNUE,
# AUCUNE distillation Scan (regles gravees). Data fraiche box-local (regenerable) ; seuls champions + trajectoire committes.
set -uo pipefail
cd /root/jass
# ----- params (memes que 0428 pour comparabilite) -----
WINDOW=35000000; FRESH=8000000
DEEP_DEPTH=12; DEEP_NUM=1; DEEP_DEN=6
SEED_FRAC=30                  # % des parties self-play demarrees depuis un seed (milieu humain / combinaison)
MID_LO=14; MID_HI=40          # bornes pieces pour echantillonner les seeds lidraughts (milieu de jeu)
SEED_CAP=400000               # cap seeds lidraughts (assez pour donner de la masse a mu sans gonfler la charge)
RW_LO=18; RW_HI=34            # bornes pieces pour le sur-echantillonnage du CONTROLE D
MAX=3                         # iterations seedees (assez pour montrer la tendance vs la base)
PLAY_DEPTH=10; EVAL_DEPTH=4; CHUNK=1000000; MAXIT=25; JUDGE_PAIRS=28
SEED_CH=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF_FEN=data/dilf_combinations.fen
# -------------------------------------------------------
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-600}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0441-seedmu-loop/artefacts"; mkdir -p "$ART"
W=/root/cw-seedmu; rm -rf "$W"; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-seedmu; TRAJ="$ART/trajectory.txt"; : > "$TRAJ"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }

preflight_build 1; preflight_train "$WINDOW" 1; preflight_note "seedmu : ${MAX}x (gen seed_frac=${SEED_FRAC} + refit + juge vs base) + controle reweight" 200; preflight_check

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

# ---------- construit le SEED-FILE : dilf (combinaisons) + lidraughts (milieux humains) ----------
say "=== construit le seed-file (dilf combinaisons + lidraughts milieux) ==="
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
[ -n "$SHARDS" ] && say "  shards lidraughts : $(echo "$SHARDS" | wc -l)" || say "  (shards lidraughts ABSENTS — 0438 pas encore committe ; seeds = dilf seul, plus mince)"
python3 - "$W/seeds.jnnw" "$DILF_FEN" "$MID_LO" "$MID_HI" "$SEED_CAP" $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools')
from pdn_to_jnnw import fen_to_bitboards, _REC_STRUCT
REC=38; out=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xC0FFEE)
recs=bytearray(); ndilf=0
for ln in open(dilf):
    b=ln.split('#',1)[0].strip()
    if not b: continue
    stm,wm,wk,bm,bk=fen_to_bitboards(b)
    recs+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); ndilf+=1
mids=[]
for sh in shards:
    try: raw=gzip.open(sh,'rb').read()
    except Exception: continue
    if raw[:4]!=b'JNNW': continue
    m=struct.unpack('<I',raw[4:8])[0]; body=memoryview(raw)[8:8+m*REC]
    for i in range(m):
        r=body[i*REC:(i+1)*REC]
        wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
        pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
        if lo<=pc<=hi: mids.append(bytes(r))
random.shuffle(mids); mids=mids[:cap]
for r in mids: recs+=r
n=ndilf+len(mids)
open(out,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(recs))
print(f"  seed-file : {n} positions (dilf={ndilf}, lidraughts_milieu={len(mids)})")
PY
NSEED=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/seeds.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${NSEED:-0}" -ge 100 ] || { say "ABORT: seed-file trop maigre (${NSEED}) — re-queue apres 0438"; exit 5; }

# ---------- helpers (copies de 0428) ----------
gen(){ local pilot="$1" nn="$2" out="$3" depth="${4:-$PLAY_DEPTH}" sf="${5:-}"; local per=$(( (nn+NCPU-1)/NCPU ))
  local seedargs=""; [ -n "$sf" ] && seedargs="--seed-file $W/seeds.jnnw --seed-frac $sf"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$EVAL_DEPTH" "$depth" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" $seedargs >/dev/null 2>&1 & done; wait
  python3 - "$out" <<'PY'
import struct,glob,sys,re
out=sys.argv[1]; REC=38; body=b""; tot=0
for f in sorted(glob.glob(out+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; body+=b[8:8+n*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
  rm -f "$out".[0-9]* ; }
app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    raw=open(acc,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
trim(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os,shutil; REC=38
acc=sys.argv[1]; Wn=int(sys.argv[2])
with open(acc,'rb') as f:
    hdr=f.read(8); n=struct.unpack('<I',hdr[4:8])[0]
    if n<=Wn: print(n); sys.exit(0)
    f.seek(8+(n-Wn)*REC); tmp=acc+'.trim'
    with open(tmp,'wb') as o:
        o.write(b'JNNW'+struct.pack('<I',Wn)); shutil.copyfileobj(f,o,1<<24)
os.replace(tmp,acc); print(Wn)
PY
}
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

# ---------- pool initial (corpus committe, identique a 0428) ----------
say "=== pool initial (corpus committe -> fenetre ${WINDOW}) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; tail "$W/assemble.log"|tee -a "$RES"; exit 8; }
cp "$W/pool.jnnw" "$W/pool_pure.jnnw"          # garde une copie PURE self-play pour le controle D
NP0=$(trim "$W/pool.jnnw" "$WINDOW"); trim "$W/pool_pure.jnnw" "$WINDOW" >/dev/null
declare -a CH; CH[0]="$W/champ0.pjtw"
say "iter 0  pool=${NP0}  base=champion-3e-5  seed_frac=${SEED_FRAC}  seeds=${NSEED}" | tee -a "$TRAJ"

# ============ LEVIER A : boucle seedee, jugee vs la BASE (champion 3e-5) ============
for k in $(seq 1 "$MAX"); do
  say "=== ITER $k : gen ${FRESH} (seed_frac=${SEED_FRAC}) mix d${PLAY_DEPTH}/d${DEEP_DEPTH} -> FIFO -> refit -> juge vs base ==="
  ND12=$(( FRESH*DEEP_NUM/DEEP_DEN )); ND10=$(( FRESH - ND12 ))
  gen "${CH[$((k-1))]}" "$ND10" "$W/new10.jnnw" "$PLAY_DEPTH" "$SEED_FRAC"
  gen "${CH[$((k-1))]}" "$ND12" "$W/new12.jnnw" "$DEEP_DEPTH" "$SEED_FRAC"
  rm -f "$W/new.jnnw"; app "$W/new10.jnnw" "$W/new.jnnw" >/dev/null; app "$W/new12.jnnw" "$W/new.jnnw" >/dev/null
  app "$W/new.jnnw" "$W/pool.jnnw" >/dev/null
  NPOOL=$(trim "$W/pool.jnnw" "$WINDOW")
  "$J" --dump-eval-features "$W/pool.jnnw" "$W/feat" >"$W/feat-k$k.log" 2>&1 || { say "ABORT dump feat k$k"; exit 8; }
  fit "$W/pool.jnnw" "$W/feat" "$W/champ$k.pjtw"; CH[$k]="$W/champ$k.pjtw"
  gzip -c "$W/champ$k.pjtw" > "$ART/champion-seedmu-iter${k}.pjtw.gz"
  VSP=$(pjudge "${CH[$k]}" "${CH[$((k-1))]}")
  VSBASE=$(pjudge "${CH[$k]}" "${CH[0]}")
  say "  ITER $k : vs_prev=${VSP}   vs_BASE(3e-5)=${VSBASE}   (pool=${NPOOL})"
  echo "iter $k  vs_prev=${VSP}  vs_base=${VSBASE}  (seed_frac=${SEED_FRAC})" | tee -a "$TRAJ" >/dev/null
  cp "$TRAJ" "$ART/trajectory.txt"
  echo "iter $k  vs_prev=${VSP}  vs_base=${VSBASE}" > "$ART/iter${k}-score.txt"
done

# ============ CONTROLE D : re-ponderation du pool self-play PUR (aucune data nouvelle) ============
say "=== CONTROLE D : sur-echantillonne le milieu (${RW_LO}-${RW_HI} pieces) du pool PUR -> refit -> juge vs base ==="
python3 - "$W/pool_pure.jnnw" "$W/pool_rw.jnnw" "$RW_LO" "$RW_HI" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
src,dst,lo,hi=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
out=open(dst,'wb'); out.write(b'JNNW'+struct.pack('<I',0)); tot=0; CH=1<<22; buf=bytearray()
def flush():
    global buf
    if buf: out.write(buf); buf=bytearray()
for i in range(n):
    r=bytes(body[i*REC:(i+1)*REC]); buf+=r; tot+=1
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32])
    pc=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    if lo<=pc<=hi: buf+=r; tot+=1          # double le poids des positions de milieu
    if len(buf)>=CH: flush()
flush(); out.seek(4); out.write(struct.pack('<I',tot)); out.close()
print(f"  pool reweighted : {tot} records (milieu {lo}-{hi} double)")
PY
"$J" --dump-eval-features "$W/pool_rw.jnnw" "$W/feat_rw" >"$W/feat-rw.log" 2>&1 || { say "ABORT dump feat rw"; exit 8; }
fit "$W/pool_rw.jnnw" "$W/feat_rw" "$W/champ_rw.pjtw"
gzip -c "$W/champ_rw.pjtw" > "$ART/champion-reweight.pjtw.gz"
RW_VSBASE=$(pjudge "$W/champ_rw.pjtw" "${CH[0]}")
say "  CONTROLE D : champion_reweight vs BASE(3e-5) = ${RW_VSBASE}"
echo "reweight vs_base=${RW_VSBASE}" >> "$TRAJ"; cp "$TRAJ" "$ART/trajectory.txt"

say ""
say "================= LECTURE ================="
say "  A (seedee) vs_base monte > 0.55 sur les iters => le SEEDING a deplace mu => point fixe self-play CASSE,"
say "       sans NNUE ni distillation. Prochain pas : juger le meilleur champion seede vs SCAN (sur ccx33)."
say "  A ~ 0.50 => seeder ces etats ne suffit pas (le linaire ne distingue pas mieux ces positions) => indice capacite/features."
say "  D (reweight) vs_base : part du gain attribuable a la simple RE-PONDERATION (sans data nouvelle)."
say "       A >> D => c'est bien la COUVERTURE nouvelle (lidraughts/dilf) qui paie, pas juste le re-equilibrage de phase."
say "==========================================="
