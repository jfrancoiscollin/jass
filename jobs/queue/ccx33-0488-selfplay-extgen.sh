#!/usr/bin/env bash
# id: ccx33-0488-selfplay-extgen
# description: LE BRAS "GEN ext_forcing ON" — A/B PROPRE vs 0486 (gen ext_forcing OFF). MEME recette exacte (meme pilote
# egdbmix, meme --quiet-only #4, memes ballots #2, meme mix masters-naturels #6, meme box ccx33 => meme dispo donnees),
# la SEULE difference = `--search-params ext_forcing=1` au gen.
# HYPOTHESE (post-0485, correction du choix §3) : pour que l'EVAL apprenne a EVITER les positions shot-vulnerables, il
# faut qu'elles soient ETIQUETEES PERDANTES ; or une position vulnerable n'est punie que si l'adversaire VOIT et JOUE la
# combinaison. ext_forcing au gen rend la recherche du pilote VOYANTE (0485 : 0.30->0.60+ sur les shots) => son self-play
# PUNIT les shots => les positions vulnerables recoivent des labels perdants => l'eval apprend a les eviter. C'est le mur
# de 0460/0462 ("on ne peut pas enseigner ses angles morts avec l'oeil aveugle") DEBLOQUE par une meilleure recherche :
# le "prof voyant" cherche depuis le sparring-vs-Scan (levier B), c'est peut-etre jass+ext_forcing sur son propre self-play.
# Contre-argument §3 (recherche propre => moins de positions vulnerables dans le corpus) : reel mais "pour punir il faut
# voir" devrait dominer. LE verdict = 0440(0488 ON) vs 0440(0486 OFF). Pilote = egdbmix. Fit logistic. Juge 0440 + vs_egdbmix.
# ROBUSTE : si expert_games.db absent, FALLBACK seeds dilf+lidraughts. AUCUN NNUE, AUCUNE distillation Scan.
set -uo pipefail
cd /root/jass
FRESH=10000000               # positions QUIETES fraiches (gen continue jusqu'a atteindre la cible malgre le filtre quiet)
PLAY_DEPTH=10; LABEL_DEPTH=4; SEED_FRAC=60
MID_LO=14; MID_HI=40; SEED_CAP=400000
JUDGE_PAIRS=28; D=11; CHUNK=1000000; MAXIT=25; L2=3e-5
SEED_CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
DB=/root/jass/data/expert_games.db
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-3000}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0488-selfplay-extgen/artefacts"; mkdir -p "$ART"
W=/root/cw-spextgen; mkdir -p "$W"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
GEOM32=/root/jass-geom32-spextgen
RES="$ART/RESULTS.txt"; CURVE="$ART/VERDICT.txt"; say(){ echo "$@" | tee -a "$RES"; }
[ -f "$RES" ] || : > "$RES"

preflight_build 1; preflight_train "$FRESH" 1
preflight_note "self-play GEN ext_forcing ON (A/B vs 0486) : quiet-only + ballots + masters + fit + juges" 800
preflight_check

# ---- build ----
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; [ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: $NP patterns"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — juge 0440 a faire ailleurs)"
git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && git show "origin/main:$SEED_CH" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT egdbmix absent"; exit 4; }

jnnw_n(){ python3 -c "import struct,sys;b=open(sys.argv[1],'rb').read();print(struct.unpack('<I',b[4:8])[0] if b[:4]==b'JNNW' and len(b)>=8 and (len(b)-8)%38==0 else -1)" "$1" 2>/dev/null || echo -1; }

# ---- #2 ballots + #6 masters depuis expert_games.db (avec FALLBACK robuste) ----
SEEDFILE=""; MASTERS=""
if [ -s "$DB" ]; then
  say "=== expert_games.db present -> #2 ballots + #6 masters-naturels ==="
  python3 tools/build_ballots.py --db "$DB" --jass "$J" --out "$W/ballots.jnnw" \
      --ply-lo 6 --ply-hi 12 --cap 1200 >"$W/ballots.log" 2>&1 && say "  $(tail -1 "$W/ballots.log")" || say "  (build_ballots echoue)"
  python3 tools/master_games_to_jnnw.py --db "$DB" --jass "$J" --out "$W/masters.jnnw" \
      --include-draws >"$W/masters.log" 2>&1 && say "  $(tail -1 "$W/masters.log")" || say "  (master_games echoue)"
  [ "$(jnnw_n "$W/ballots.jnnw")" -gt 100 ] 2>/dev/null && SEEDFILE="$W/ballots.jnnw" || say "  ballots invalides/vides -> fallback seeds"
  [ "$(jnnw_n "$W/masters.jnnw")" -gt 10000 ] 2>/dev/null && MASTERS="$W/masters.jnnw" || say "  masters invalides/vides -> mix saute"
else
  say "=== expert_games.db ABSENT (box-local non survivante) -> FALLBACK seeds dilf+lidraughts, pas de masters ==="
fi

# fallback seed-file = dilf + lidraughts milieux (comme 0481)
if [ -z "$SEEDFILE" ]; then
  SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
  python3 - "$W" "$DILF" "$MID_LO" "$MID_HI" "$SEED_CAP" $SHARDS <<'PY' | tee -a "$RES"
import sys,struct,gzip,random
sys.path.insert(0,'tools'); from pdn_to_jnnw import fen_to_bitboards,_REC_STRUCT
REC=38; W=sys.argv[1]; dilf=sys.argv[2]; lo=int(sys.argv[3]); hi=int(sys.argv[4]); cap=int(sys.argv[5]); shards=sys.argv[6:]
random.seed(0xBEEF); drecs=bytearray(); nd=0
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
print(f"  fallback seeds : dilf={nd} lidraughts={len(mids)} both={nd+len(mids)}")
PY
  SEEDFILE="$W/seeds_both.jnnw"
fi
say "  seed-file = $SEEDFILE ($(jnnw_n "$SEEDFILE") positions) ; masters = ${MASTERS:-<aucun>}"

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
conv_ci(){ python3 - "$1" "$DILF" <<'PY'
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

# ---- gen self-play QUIET-ONLY depuis ballots, ext_forcing ON au gen (le SEUL changement vs 0486) ----
# La recherche du pilote VOIT et PUNIT les shots (0485) => positions vulnerables = labels perdants => l'eval apprend a eviter.
# ext_forcing au gen coute des noeuds (lignes forcantes etendues) => le gen est un peu plus lent qu'a 0486 (acceptable).
say "=== gen self-play ${FRESH} (--quiet-only, ballots frac ${SEED_FRAC}%, pilote egdbmix, ext_forcing ON au gen) ==="
per=$(( (FRESH+NCPU-1)/NCPU ))
for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/corpus.jnnw.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" \
    --nnue "$W/egdbmix.pjtw" --quiet-only --search-params "ext_forcing=1" --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies 6 --explore-eps 4 >/dev/null 2>&1 & done; wait
merge "$W/corpus.jnnw"
NSP=$(jnnw_n "$W/corpus.jnnw"); say "  self-play quiet = $NSP positions"
[ "${NSP:-0}" -ge 1000000 ] || { say "ABORT: self-play vide ($NSP)"; exit 7; }

# ---- #6 mix masters-naturels (frequence naturelle, pas d'oversampling) ----
if [ -n "$MASTERS" ]; then
  NM=$(jnnw_n "$MASTERS"); app "$MASTERS" "$W/corpus.jnnw" >/dev/null
  say "  + masters-naturels = $NM positions (frequence naturelle ~$(python3 -c "print(f'{100*$NM/($NSP+$NM):.0f}')")%)"
fi
NTOT=$(jnnw_n "$W/corpus.jnnw"); say "  corpus total = $NTOT"

# ---- fit ----
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ.pjtw" \
    >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
gzip -c "$W/champ.pjtw" > "$ART/champion-selfplay-clean.pjtw.gz"
rm -f "$W/feat" "$W/corpus.jnnw"

# ---- juges : 0440 vs Scan + vs_egdbmix ----
VB=$(pjudge "$W/champ.pjtw" "$W/egdbmix.pjtw")
if [ "$HAVE_SCAN" = 1 ]; then
  ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-clean" >"$W/cv.log" 2>&1 ) || say "  (juge 0440 echoue)"
  read M LO HI N < <(conv_ci "$ART/conv-clean")
else M=NA; LO=NA; HI=NA; N=0; fi

say ""; say "================= VERDICT (A/B gen ext_forcing ON vs 0486 OFF) ================="
{ echo "recette : gen ext_forcing ON + quiet-only + seeds=$([ "$SEEDFILE" = "$W/ballots.jnnw" ] && echo BALLOTS || echo dilf+lidraughts) + masters=$([ -n "$MASTERS" ] && echo OUI || echo non)"
  echo "0440 (gen ON, 0488) = $M  IC95=[$LO,$HI]  (n=$N)   [base egdbmix = 0.302 ; comparer a 0486 gen OFF]"
  echo "vs_egdbmix (self-play) = $VB"
  echo "LECTURE : 0440(ON) > 0440(OFF) hors-IC => le prof VOYANT (ext_forcing au gen) PUNIT les shots => l'eval apprend a"
  echo "          eviter les positions shot-vulnerables => DEBLOCAGE de l'auto-supervision (mur 0460/0462 leve). On industrialise."
  echo "          0440(ON) ~ 0440(OFF) => le §3 l'emporte (recherche propre = moins de signal) OU l'eval ne capte pas => l'extension"
  echo "          reste un levier de JEU (a baker, cf 0487), pas de GEN. Comparer aussi les deux a 0.302 (la recette data pure)."
} | tee "$CURVE" | tee -a "$RES"
say "==========================================="
