#!/usr/bin/env bash
# id: cpx62-0548-poolfit
# description: FIT POOLE (JFC 'on poole les 2 gen-data pour plus de puissance ; ccx33 alimente cpx62'). cpx62 GENERE son
# propre corpus 3M (config combo-aware : pilote=champion, asym CONSERVEE, combo-seeded, qs_sacs bake), le COMMIT, puis
# ATTEND + TIRE le corpus du feeder ccx33-0547 (poll git, jusqu'a 5h ; fallback = cpx62 seul si absent). POOL = cpx62 +
# ccx33 + enrichissement combo (combos.jnnw 0464) => ~7M positions. Fit train_stream avec PRIOR SEQUENTIEL vers le champion
# (--prior-mean, bit self-desc strippe). JUGE gen1-pooled vs champion (Elo) — a comparer au gen1 3M de 0545 pour mesurer
# le gain de puissance du pooling. AUCUN NNUE. 100% lineaire. Reprise-safe.
# expected_duration: ~8-14 h (gen 3M + attente feeder + fit 7M + juge).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0548-poolfit/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-pool; rm -rf "$W"; mkdir -p "$W"
GEOM32=/root/jass-geom32-pool
# ---- params ----
FRESH=3000000; PLAY_DEPTH=10; LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"     # asym punisher (CONSERVE, choix JFC)
SEED_FRAC=25
CHUNK=1000000; MAXIT=25; L2=3e-5
PRIOR_VISIT=0.25; PRIOR_DECAY=1.0
JUDGE_PAIRS=4; JUDGE_DEPTH=9
CHAMP_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
COMBO_ENRICH_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
DILF=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"

# ---------- build jass depuis main (qs_sacs baké ON, 32-pat, features champion) ----------
say "=== build jass depuis main (qs_sacs baké ON, 32-pat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT: attendait 32 patterns, a $NP"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champ egdbmix absent"; exit 4; }
CHAMP="$W/champ.pjtw"
# Le loader python du prior (load_v3_weights_float) est STRICT sur le champ version : il exige ver==3, or le champion
# porte le bit self-desc (0x200) => ver=515. Le fichier EST du v3 valide (n_pat=17,006,112=NP*NB, n_ext=120, layout
# standard offset 20). On fabrique une copie avec le bit strippe (ver=3) UNIQUEMENT pour --prior-mean. L'original
# (ver=515) reste le PILOTE et l'adversaire du JUGE (l'engine, lui, charge le format deploye sans souci).
python3 -c "import struct; r=bytearray(open('$CHAMP','rb').read()); struct.pack_into('<I',r,4,3); open('$W/champ_prior.pjtw','wb').write(r)" \
  || { say "ABORT strip champ prior"; exit 4; }
CHAMP_PRIOR="$W/champ_prior.pjtw"
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  sanity qs_sacs (defaut ON) : $(head -1 "$DILF" | sed 's/#.*//' | "$J" --dump-sacs 2>/dev/null | head -1)"

# ---------- primitives (reprises de 0536) ----------
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
# moniteur de volume : echantillonne la taille des shards en cours -> positions ~ (octets-8)/38,
# ecrit dans $ART/progress.txt (committe par le runner au heartbeat) => volume + debit + ETA visibles en git.
mon_start(){ local prefix="$1" tag="$2" target="$3"
  ( T0=$SECONDS; while :; do
      P=$(python3 -c "import glob,os
t=0
for f in glob.glob('$prefix.*'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)" 2>/dev/null || echo 0)
      DT=$((SECONDS-T0)); RATE=$(( P/(DT>0?DT:1) ))
      ETA=$(( RATE>0 ? (target-P)/RATE : -1 ))
      echo "$(date -u +%H:%M:%SZ) [$tag] positions~${P}/${target}  debit~${RATE}/s  ETA~${ETA}s" >> "$ART/progress.txt"
      sleep 120
    done ) & MON_PID=$!; }
mon_stop(){ kill "$MON_PID" 2>/dev/null || true; MON_PID=""; }
gen_strong(){ local pilot="$1" nn="$2" out="$3"; local per=$(( (nn+NCPU-1)/NCPU ))
  mon_start "$out" "gen" "$nn"
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$out.$s" "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$pilot" --asym-punisher-params "$FORCE_SPEC" --quiet-only \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >/dev/null 2>&1 & done; wait
  mon_stop
  merge "$out"; }
fit(){ env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$1" --feat "$2" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prior-mean "$CHAMP_PRIOR" --prior-visit-scale "$PRIOR_VISIT" --prior-decay "$PRIOR_DECAY" --out "$3" \
    >"${3%.pjtw}.log" 2>&1 || { say "TRAIN FAIL $3"; tail -14 "${3%.pjtw}.log"|sed 's/^/  /'; exit 9; }; }
pjudge(){ for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$1" \
    --jass-b "$J" --pattern-b "$2" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" >"$W/j.$s" 2>&1 & done; wait
  python3 - "$W"/j.* <<'PY'
import sys,math; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; se=0.5/(g**0.5) if g else 1
elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"  new-vs-champion : games={g}  A(new)={a} B(champ)={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}")
PY
  rm -f "$W"/j.* ; }

# ---------- seed-file (dilf combos + lidraughts midgames) : diversite + enrich openings combo ----------
say ""
say "=== seed-file (dilf combos + lidraughts) ==="
SHARDS=$(ls $SHARD_GLOB 2>/dev/null || true)
python3 - "$W" "$DILF" 14 40 300000 $SHARDS <<'PY' | tee -a "$RES"
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
open(f"{W}/seeds.jnnw",'wb').write(b'JNNW'+struct.pack('<I',nd+len(mids))+bytes(drecs)+b"".join(mids))
print(f"  seed-file : dilf={nd} lidraughts={len(mids)}")
PY
SEEDFILE="$W/seeds.jnnw"; [ -s "$SEEDFILE" ] || { say "ABORT seed-file vide"; exit 7; }

# ---------- combo enrichment corpus ----------
git show "origin/main:$COMBO_ENRICH_SRC" > "$W/combos.jnnw" 2>/dev/null && [ -s "$W/combos.jnnw" ] \
  && say "  combo-enrich : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0) positions (0464)" \
  || { say "  (combos.jnnw absent -> enrichissement sauté)"; : > "$W/combos.jnnw"; }

# ---------- GENERATION 1 (pilote=champion, asym, quiet-only, combo-seeded) ----------
say ""
say "================= GENERATION 1 (pilote=champion egdbmix, asym CONSERVE) ================="
gen_strong "$CHAMP" "$FRESH" "$W/selfplay.jnnw"
NSP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/selfplay.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  self-play (quiet-only, qs_sacs ON) : ${NSP} pos"
[ "${NSP:-0}" -ge 500000 ] || { say "ABORT: corpus self-play trop petit ($NSP)"; exit 7; }

# ---------- COMMIT du corpus cpx62 (reuse pour le pool + reproductibilite) ----------
gzip -c "$W/selfplay.jnnw" > "$ART/corpus-cpx62.jnnw.gz"
say "  corpus cpx62 committe : $(du -h "$ART/corpus-cpx62.jnnw.gz" | cut -f1)"

fit_and_judge(){ local corpus="$1" tag="$2"   # -> fit (prior) + juge vs champion, commit champion-$tag
  "$J" --dump-eval-features "$corpus" "$W/feat_$tag" >"$W/feat_$tag.log" 2>&1 || { say "ABORT dump feat $tag"; exit 8; }
  say ""; say "=== FIT [$tag] train_stream (PRIOR SEQUENTIEL, visit=$PRIOR_VISIT decay=$PRIOR_DECAY) ==="
  fit "$corpus" "$W/feat_$tag" "$W/$tag.pjtw"; rm -f "$W/feat_$tag"
  grep -iE 'prior|iter|loss' "$W/$tag.log" | tail -5 | sed 's/^/  /' | tee -a "$RES"
  gzip -c "$W/$tag.pjtw" > "$ART/champion-$tag.pjtw.gz"; say "  champion-$tag committe"
  say "=== JUGE [$tag] vs champion egdbmix @ d$JUDGE_DEPTH, dilf x${JUDGE_PAIRS}pair ==="
  pjudge "$W/$tag.pjtw" "$CHAMP" | tee -a "$RES"; }

# ========== FIT #1 : cpx62 3M SEUL + combos — RESULTAT IMMEDIAT, on N'ATTEND PAS ccx33 (choix JFC) ==========
say ""; say "############ FIT #1 : cpx62 3M seul (+combos) — premier resultat, sans attendre ccx33 ############"
concat "$W/corpus_solo.jnnw" "$W/selfplay.jnnw" "$W/combos.jnnw" | tee -a "$RES"
fit_and_judge "$W/corpus_solo.jnnw" "gen1-cpx62"
rm -f "$W/corpus_solo.jnnw"

# ========== FIT #2 : POOL cpx62 + ccx33 + combos (attend le feeder ; fallback = on garde juste le #1) ==========
CCX33_CORPUS=jobs/results/ccx33-0547-gendata/artefacts/corpus-gen1b.jnnw.gz
say ""; say "############ FIT #2 : POOL — attente du corpus feeder ccx33 ($CCX33_CORPUS) ############"
GOT=""; DEADLINE=$((SECONDS+18000))   # attend jusqu'a 5h
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  git fetch origin main --quiet 2>/dev/null || true
  if git cat-file -e "origin/main:$CCX33_CORPUS" 2>/dev/null; then
    git show "origin/main:$CCX33_CORPUS" | gunzip > "$W/ccx33.jnnw" 2>/dev/null \
      && [ -s "$W/ccx33.jnnw" ] && { GOT=1; break; }
  fi
  say "  (feeder pas encore pret, re-check dans 300s ; SECONDS=$SECONDS)"; sleep 300
done
if [ -n "$GOT" ]; then
  NCX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/ccx33.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
  say "  corpus ccx33 recu : ${NCX} pos -> POOL cpx62+ccx33+combos"
  concat "$W/corpus_pool.jnnw" "$W/selfplay.jnnw" "$W/ccx33.jnnw" "$W/combos.jnnw" | tee -a "$RES"
  fit_and_judge "$W/corpus_pool.jnnw" "gen1-pooled"
  say ""; say "  => COMPARER : gen1-cpx62 (3M) vs gen1-pooled (~7M) vs champion. Le pool ajoute-t-il de la puissance ?"
else
  say "  ⚠ feeder ccx33 indisponible apres 5h -> pas de FIT #2 ; on garde le resultat #1 (cpx62 seul)."
fi
say ""
say "  => rate>0.5 hors-IC = la passe combo-aware ameliore l'eval => on chaine (gen2+). Sinon read negatif propre."
say "=== fin poolfit (fit #1 immediat + fit #2 poole) ==="
