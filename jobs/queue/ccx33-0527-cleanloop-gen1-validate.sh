#!/usr/bin/env bash
# id: ccx33-0527-cleanloop-gen1-validate
# description: VALIDATION 1 TOUR de la BOUCLE PROPRE from-scratch (formule figée JFC 2026-07-01). Objectif = prouver que
# l'ORCHESTRATION tourne end-to-end avec la RECETTE FORTE avant de lâcher la chaîne (choix JFC "monter + valider 1 tour").
# Seed = MATÉRIEL PUR (men=1, roi=3, zéro prior positionnel — choix JFC, le seed de Scan). Recette forte (vs 0481/0482) :
#   #1 ext_forcing au JEU via ASYMÉTRIE (--asym-punisher-params : punisher voyant ext_forcing / victim aveugle => fabrique
#      le signal 'shot atteint -> puni -> label défaite' que le self-play symétrique n'a pas ; réponse au mur 0460/0462) ;
#   #2 ballots (ouvertures déséquilibrées, ply 6-12, miroir couleur) en --seed-file ;
#   #4 --quiet-only ; #6 mix maîtres à fréquence naturelle (résultat réel) ; + mix egdb-finale (baké 0454).
# Fit train_stream 32cf color-fold men-only. Juge 0440 vs Scan + vs_egdbmix. UNE génération (KGEN=1, volume réduit 3M pour
# un retour rapide). ⚠️ gen-1 depuis un seed MATÉRIEL sera FAIBLE (0440 bas) — NORMAL : on valide la MACHINERIE, pas la force
# (la montée se fait sur les générations ; la chaîne = job suivant). Composants maîtres/egdb NON-FATAUX (fallback + log).
# 100% LINÉAIRE. AUCUN NNUE. AUCUNE distillation Scan. expected_duration: ~1.5-3 h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0527-cleanloop-gen1-validate/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-cleanloop; rm -rf "$W"; mkdir -p "$W"
GEOM32=/root/jass-geom32-cleanloop

# ----- params -----
FRESH=3000000; PLAY_DEPTH=10; LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
SEED_CORPUS=1200000; SEED_FRAC=25
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"
MASTER_MAX=0            # 0 = toutes les parties maîtres (fréquence naturelle)
EGDB_POOL=600000
CHUNK=1000000; MAXIT=25; L2=3e-5
JUDGE_PAIRS=28; D=11
EXPERT_DB=data/expert_games.db
DILF_FEN=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
SEED_CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"

# ---------- build 32-pat (flags champion + egdb) ----------
say "=== build jass (32-pat, egdb ON) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/sc.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null||true; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1; }
git cat-file -e "origin/main:$SEED_CH" 2>/dev/null && git show "origin/main:$SEED_CH" | gunzip > "$W/egdbmix.pjtw" || { say "  (egdbmix absent — vs_base saute)"; : > "$W/egdbmix.pjtw"; }

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
# concat JNNW arbitraires -> $1 (ignore les absents/vides)
concat(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,sys
out=sys.argv[1]; ins=sys.argv[2:]; REC=38; body=b""; tot=0; parts=[]
for f in ins:
    try: b=open(f,'rb').read()
    except Exception: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print("  concat -> "+str(tot)+" : "+", ".join(f"{k}={v}" for k,v in parts))
PY
}
# gen self-play FORTE : asym punisher(ext_forcing)/victim + quiet-only + ballots seed-file
gen_strong(){ local pilot="$1" nn="$2" out="$3"
  local per=$(( (nn+NCPU-1)/NCPU )); local nnopt=""
  [ "$pilot" != "DEFAULT" ] && nnopt="--nnue $pilot"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      $nnopt --asym-punisher-params "$FORCE_SPEC" --quiet-only \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >/dev/null 2>&1 & done; wait
  merge "$out"; }
# gen simple (pour forger le seed ; label réétiqueté ensuite)
gen_plain(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn+NCPU-1)/NCPU )); local nnopt=""
  [ "$pilot" != "DEFAULT" ] && nnopt="--nnue $pilot"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      $nnopt --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" >/dev/null 2>&1 & done; wait
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
conv_rate(){ python3 - "$1" "$DILF_FEN" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=sw=an=sn=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    att=1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else (0.5 if out=="D" else 0.0)
    if (jiw and s=="W") or ((not jiw) and s=="B"): aw+=att; an+=1
    else: sw+=att; sn+=1
print(f"{(aw/an if an else 0):.3f} {an} {(sw/sn if sn else 0):.3f} {sn}")
PY
}

# ---------- #2 BALLOTS (fallback dilf+lidraughts si expert_games.db absent) ----------
if [ -f "$EXPERT_DB" ]; then
  say "=== #2 ballots depuis $EXPERT_DB (ply 6-12, déséquilibrées, miroir) ==="
  python3 tools/build_ballots.py --db "$EXPERT_DB" --jass "$J" --out "$W/ballots.jnnw" \
    --ply-lo 6 --ply-hi 12 --min-imbalance 1 --cap 400000 >"$W/ballots.log" 2>&1 \
    && SEEDFILE="$W/ballots.jnnw" || { say "  (build_ballots a échoué -> fallback dilf+lidraughts)"; SEEDFILE=""; }
  [ -s "$SEEDFILE" ] || SEEDFILE=""
  [ -n "$SEEDFILE" ] && say "  ballots : $(python3 -c "import struct;print(struct.unpack('<I',open('$SEEDFILE','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) positions"
else
  say "  (expert_games.db absent -> ballots sautés, fallback dilf+lidraughts)"; SEEDFILE=""
fi
if [ -z "$SEEDFILE" ]; then
  SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
  python3 - "$W" "$DILF_FEN" 14 40 400000 $SHARDS <<'PY' | tee -a "$RES"
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
open(f"{W}/seeds_both.jnnw",'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(drecs)+b"".join(mids))
print(f"  fallback seeds : dilf={nd} lidraughts={len(mids)}")
PY
  SEEDFILE="$W/seeds_both.jnnw"
fi

# ---------- FORGE SEED MATÉRIEL PUR (men=1, roi=3) ----------
say "=== forge seed matériel pur (gen ${SEED_CORPUS} eval-défaut -> réétiquette signe matériel -> fit) ==="
SEED_MAT="$W/seed-materiel.pjtw"
gen_plain "DEFAULT" "$SEED_CORPUS" "$W/matcorp.jnnw"
python3 - "$W/matcorp.jnnw" <<'PY' | tee -a "$RES"
import struct,sys; REC=38
p=sys.argv[1]; raw=bytearray(open(p,'rb').read()); n=struct.unpack('<I',raw[4:8])[0]
p1=p0=eq=0
for i in range(n):
    o=8+i*REC; wm,wk,bm,bk=struct.unpack('<QQQQ',raw[o:o+32]); stm=raw[o+32]
    mw=bin(wm).count('1')+3*bin(wk).count('1'); mb=bin(bm).count('1')+3*bin(bk).count('1')
    diff=(mw-mb) if stm==0 else (mb-mw); w=1 if diff>0 else (-1 if diff<0 else 0)
    raw[o+37:o+38]=struct.pack('<b',w); p1+=w>0; p0+=w<0; eq+=w==0
open(p,'wb').write(raw); print(f"  réétiquette matériel : n={n} (+={p1} -={p0} nul={eq})")
PY
"$J" --dump-eval-features "$W/matcorp.jnnw" "$W/matfeat" >"$W/matfeat.log" 2>&1 || { say "ABORT dump feat seed"; exit 8; }
fit "$W/matcorp.jnnw" "$W/matfeat" "$SEED_MAT"; rm -f "$W/matfeat" "$W/matcorp.jnnw"
EW=$("$J" --eval-position "$SEED_MAT" "W:W31,32,33:B18,19" 2>/dev/null | tr -dc '0-9-')
EB=$("$J" --eval-position "$SEED_MAT" "B:W31,32,33:B18,19" 2>/dev/null | tr -dc '0-9-')
say "  vérif seed : eval(blanc+1h)=${EW}cp  eval(noir-1h)=${EB}cp  (attendu >0 et <0)"
awk "BEGIN{exit !(${EW:-0}+0 > 0 && ${EB:-0}+0 < 0 && (${EW:-0}-(${EB:-0})) >= 10)}" || { say "ABORT: seed matériel dégénéré"; exit 9; }
gzip -c "$SEED_MAT" > "$ART/seed-materiel.pjtw.gz"; say "  seed matériel OK -> pilote gen 1"

# ---------- GÉNÉRATION 1 (recette forte) ----------
say ""; say "================= GÉNÉRATION 1 (pilote=seed-matériel-pur, recette forte) ================="
say "  gen self-play ${FRESH} : asym punisher[$FORCE_SPEC]/victim + quiet-only + ballots"
gen_strong "$SEED_MAT" "$FRESH" "$W/selfplay.jnnw"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/selfplay.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  self-play (après quiet-only) : ${NSP} positions"
[ "${NSP:-0}" -ge 500000 ] || { say "ABORT gen1 : corpus trop petit ($NSP)"; exit 7; }

# ---------- #6 mix MAÎTRES (fréquence naturelle) — non-fatal ----------
MASTERS=""
if [ -f "$EXPERT_DB" ]; then
  say "=== #6 parties maîtres -> positions quiètes (résultat réel, fréquence naturelle) ==="
  if python3 tools/master_games_to_jnnw.py --db "$EXPERT_DB" --jass "$J" --out "$W/masters.jnnw" \
       --min-plies 24 --skip-open 8 --skip-endgame-pieces 8 --max-games "$MASTER_MAX" >"$W/masters.log" 2>&1 && [ -s "$W/masters.jnnw" ]; then
    MASTERS="$W/masters.jnnw"; say "  maîtres : $(python3 -c "import struct;print(struct.unpack('<I',open('$MASTERS','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) positions"
  else say "  (master_games_to_jnnw échoué/vide -> mix maîtres sauté)"; tail -4 "$W/masters.log" 2>/dev/null|sed 's/^/    /'|tee -a "$RES"; fi
else say "  (expert_games.db absent -> mix maîtres sauté)"; fi

# ---------- mix EGDB-FINALE (baké 0454) — non-fatal ----------
EGMIX=""
if [ -n "$EGDIR" ]; then
  say "=== mix egdb-finale (gen-egdb-wld, <=7 pièces exactes) ==="
  if "$J" --gen-egdb-wld "$EGDB_POOL" "$W/egdb.jnnw" "$EGDIR" 7 2048 12345 >"$W/egdb.log" 2>&1 && [ -s "$W/egdb.jnnw" ]; then
    EGMIX="$W/egdb.jnnw"; say "  egdb-finale : $(python3 -c "import struct;print(struct.unpack('<I',open('$EGMIX','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) positions"
  else say "  (gen-egdb-wld échoué -> mix egdb sauté)"; tail -4 "$W/egdb.log" 2>/dev/null|sed 's/^/    /'|tee -a "$RES"; fi
else say "  (egdb absent -> mix egdb sauté)"; fi

# ---------- corpus final = self-play + maîtres + egdb ----------
say "=== corpus gen1 = self-play + maîtres + egdb ==="
concat "$W/corpus.jnnw" "$W/selfplay.jnnw" $MASTERS $EGMIX | tee -a "$RES"

# ---------- fit -> champion gen1 ----------
say "=== fit train_stream (32cf color-fold men-only) -> champion-gen1 ==="
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat gen1"; exit 8; }
fit "$W/corpus.jnnw" "$W/feat" "$W/champ1.pjtw"
gzip -c "$W/champ1.pjtw" > "$ART/champion-gen1.pjtw.gz"

# ---------- juges ----------
VB=$(pjudge "$W/champ1.pjtw" "$W/egdbmix.pjtw")
say "  vs_egdbmix (self-play arch, d9) = $VB"
if [ "$HAVE_SCAN" = 1 ]; then
  say "=== juge 0440 vs Scan (d${D}, no-DB) ==="
  ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ1.pjtw" \
      --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF_FEN" --dump-games-dir "$ART/conv-gen1" >"$W/cv1.log" 2>&1 ) || say "  (juge 0440 échoué)"
  read JA JN SA SN < <(conv_rate "$ART/conv-gen1")
  say "  0440 gen1 : JASS-au-trait=$JA (n=$JN)  SCAN-au-trait=$SA (n=$SN)"
else say "  (Scan absent -> 0440 à refaire ailleurs)"; fi

say ""; say "================= VALIDATION 1 TOUR — VERDICT ================="
say "  Composants exercés : seed-matériel[OK] · ballots[$([ -n "$SEEDFILE" ] && echo OK || echo fallback)] ·"
say "    gen asym+quiet-only[OK ${NSP}pos] · maîtres[$([ -n "$MASTERS" ] && echo OK || echo skip)] · egdb[$([ -n "$EGMIX" ] && echo OK || echo skip)] · fit[OK] · juge[$([ "$HAVE_SCAN" = 1 ] && echo OK || echo skip)]"
say "  ⚠️ gen-1 depuis seed matériel = FAIBLE attendu (0440 bas) : on valide la MACHINERIE, pas la force."
say "  Si tous composants OK + 0440 produit + vs_egdbmix sensé => orchestration VALIDÉE => monter la CHAÎNE (KGEN~10-20,"
say "    2-box split-gen, auto-stop). Sinon => corriger le composant fautif avant d'enchaîner."
say "==========================================================="
