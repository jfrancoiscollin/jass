#!/usr/bin/env bash
# id: ccx33-0595-tb-regen-app
# description: REDO PROPRE de la manche tb-relabel (JFC "fait 1 quand meme"). 0589 avait tb_relabel=0 (chemin EGDB faux :
# parent au lieu de /app). ICI on utilise JASS_EGDB_PATH=/root/egdb_extracted/app (fix prouve par 0594 : 42673 resolved,
# 2747 stalls). NB : le "+18" de 0587 etait un PHANTOM (tb_relabel=0 aussi) — ceci est le PREMIER vrai test du lever.
# Package champion identique (mirror 0566/0568 : mix 60/20/20 pd8/9/10 2M, asym punisher, quiet-only, seed dilf+lidraughts,
# eps5, open8) + --tb-relabel (labels finale EXACTS <=6 pieces via EGDB). Fit prior gen1 + combos. GARDE-FOU : probe EGDB
# avant la gen + fail-fast si tb_relabel=0 sur pd8. JUGE moteur COIN par
# defaut (candidat, gen1, champion-regen dans le MEME build) :
#   (1) cand-tb vs gen1        = GATE PRIMAIRE (plain-regen etait NEUTRE 0.5041 vs gen1 en 0570 ; tb compose-t-il enfin ?)
#   (2) cand-tb vs champ-regen = valeur MARGINALE de tb-relabel au-dessus du plain regen (meme package, seul tb ajoute)
# GATE : (1) borne basse IC>0.50 => tb-relabel a debloque le plateau au scale => PROMO nouveau champion EVAL, chaine.
# VERIF FIX#4 agit : LABELHYG tb_relabel>0 par phase (sinon egdb pas trouve => ABORT). Code gen depuis DEVELOP (main.cpp).
# Fit = train_stream de main (identique a champion-regen). AUCUN NNUE. ~4-6h ccx33 (8 coeurs).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0595-tb-regen-app/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0595-tb-regen-app/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-tbregenapp; rm -rf "$W"; mkdir -p "$W"; GEOM32=/root/jass-geom32-tbregenapp
LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200; SEED_FRAC=25
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"
L2=3e-5; MAXIT=25; CHUNK=1000000; PRIOR_VISIT=0.25; PRIOR_DECAY=1.0
JUDGE_DEPTH=9; JUDGE_PAIRS=4
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
REGEN_CH_GZ=jobs/results/cpx62-0568-fit-regen-oncoin/artefacts/champion-regen.pjtw.gz
COMBO_SRC=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
DILF=data/dilf_combinations.fen

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_into(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,glob,sys
out=sys.argv[1]; REC=38; body=b""; tot=0; files=[]
for p in sys.argv[2:]: files+=sorted(glob.glob(p))
for f in files:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}
count_pos(){ python3 -c "import glob,os
t=0
for f in glob.glob('$1'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)" 2>/dev/null || echo 0; }

say "=== MANCHE PROD tb-relabel : build EGDB (code gen=develop), moteur COIN ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build non actif"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git checkout -- src/main.cpp 2>/dev/null || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; exit 7; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
EGDBP=/root/egdb_extracted/app   # FIX (0594) : les fichiers DB sont dans app/, pas dans le parent
ls "$EGDBP"/db2.idx1 "$EGDBP"/db5.idx1 >/dev/null 2>&1 || { say "ABORT base EGDB absente dans $EGDBP"; exit 5; }
export JASS_EGDB_PATH="$EGDBP"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$REGEN_CH_GZ" | gunzip > "$W/champregen.pjtw" 2>/dev/null || : > "$W/champregen.pjtw"
git show "origin/main:$COMBO_SRC" > "$W/combos.jnnw" 2>/dev/null || : > "$W/combos.jnnw"
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  moteur coin : $(git show origin/main:src/search_params.hpp | grep -cE 'probcut_min_depth = 5|eg_no_nmp  = false|qs_threat_ext = true')/3 params-cle ; NUM_PATTERNS=$NP ; egdb=$EGDBP"
say "  combos=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0)"
# ---- PROBE EGDB fonctionnel (fail-fast avant 3h de gen) : egdb-relabel sur combos => resolved>0 sinon abort ----
"$J" --egdb-relabel "$W/combos.jnnw" "$EGDBP" "$W/_probe.jnnw" 256 >"$W/egdbprobe.log" 2>&1 || true
PROBE_RES=$(grep -oE '[0-9]+ egdb-resolved' "$W/egdbprobe.log" | grep -oE '[0-9]+' | head -1)
say "  EGDB probe (combos) : $(grep -oE '[0-9]+ egdb-resolved[^,]*' "$W/egdbprobe.log" | head -1 || echo AUCUN)"
[ "${PROBE_RES:-0}" -gt 0 ] 2>/dev/null || { say "ABORT EGDB ne resout rien sur $EGDBP (init KO) : $(sed -n '1p' "$W/egdbprobe.log")"; exit 5; }
rm -f "$W/_probe.jnnw"

# ---- seed-file (dilf + lidraughts mids) : IDENTIQUE 0566 ----
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
SEEDFILE="$W/seeds.jnnw"; [ -s "$SEEDFILE" ] || { say "ABORT seed vide"; exit 7; }

# ---- GEN : mix 60/20/20 pd8/9/10 = 2M, package champion + --tb-relabel (EGDB actif via JASS_EGDB_PATH) ----
gen_phase(){ local pd="$1" nn="$2" tag="$3"; local per=$(( (nn+NCPU-1)/NCPU )); local pids=()
  say ""; say "=== GEN PHASE $tag : ${nn} pos @ pd${pd} +tb-relabel (x$NCPU shards, coin bake) ==="
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/${tag}.jnnw.$s" "$LABEL_DEPTH" "$pd" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE_SPEC" --quiet-only --tb-relabel \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >"$W/g_${tag}_$s.log" 2>&1 & pids+=($!); done
  ( T0=$SECONDS; CY=0; while kill -0 "${pids[0]}" 2>/dev/null; do
      sleep 300; CY=$((CY+1)); P=$(count_pos "$W/${tag}.jnnw.*"); DT=$((SECONDS-T0)); R=$(( P/(DT>0?DT:1) ))
      printf '%s [%s] positions~%s/%s debit~%s/s\n' "$(date -u +%H:%M:%SZ)" "$tag" "$P" "$nn" "$R" > "$ART/progress-${tag}-$(printf %03d $CY).txt"
    done ) & local MON=$!
  wait "${pids[@]}"; kill "$MON" 2>/dev/null || true; wait "$MON" 2>/dev/null || true
  local NP2; NP2=$(merge_into "$W/${tag}.jnnw" "$W/${tag}.jnnw.*"); rm -f "$W/${tag}.jnnw."[0-9]*
  say "  phase $tag : ${NP2} pos ; $(grep -h LABELHYG "$W/g_${tag}_1.log"|head -1)"
  local TBR; TBR=$(grep -hoE 'tb_relabel=[0-9]+' "$W/g_${tag}_1.log"|head -1|cut -d= -f2)
  if [ -n "${TBR:-}" ] && [ "$TBR" -gt 0 ] 2>/dev/null; then say "  ✓ tb_relabel=$TBR>0 (FIX#4 actif sur shard1)"
  else say "  ❌ tb_relabel=0 sur shard1 phase $tag => EGDB n'agit pas => ABORT (fail-fast)"; exit 5; fi
  gzip -c "$W/${tag}.jnnw" > "$ART/phase-${tag}.jnnw.gz"
  commit_to_main "$ART/phase-${tag}.jnnw.gz" "$ARTREL/phase-${tag}.jnnw.gz" "tb-regen: phase $tag committee (${NP2} pos, +tb-relabel)" \
    && say "  phase $tag committee job-side" || say "  (commit phase $tag echoue)"
}
gen_phase 8 1200000 "pd8"
gen_phase 9 400000  "pd9"
gen_phase 10 400000 "pd10"

say ""; say "=== MERGE corpus tb-regen 2M ==="
NTOT=$(merge_into "$W/tbregen.jnnw" "$W/pd8.jnnw" "$W/pd9.jnnw" "$W/pd10.jnnw")
say "  corpus tb-regen : ${NTOT} pos"
gzip -c "$W/tbregen.jnnw" > "$ART/corpus-tbregen-2M.jnnw.gz"
commit_to_main "$ART/corpus-tbregen-2M.jnnw.gz" "$ARTREL/corpus-tbregen-2M.jnnw.gz" "tb-regen: corpus 2M 60/20/20 pd8/9/10 +tb-relabel (${NTOT} pos)" \
  && say "  corpus committe job-side ($(du -h "$ART/corpus-tbregen-2M.jnnw.gz"|cut -f1))" || say "  (commit corpus echoue)"

# ---- FIT prior gen1 + combos : IDENTIQUE 0568 (train_stream de main) ----
python3 -c "import struct; r=bytearray(open('$W/gen1.pjtw','rb').read()); struct.pack_into('<I',r,4,3); open('$W/gen1_prior.pjtw','wb').write(r)"
concat(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,sys
out=sys.argv[1]; body=b""; tot=0; parts=[]
for f in sys.argv[2:]:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print("  concat -> "+str(tot)+" : "+", ".join(f"{k}={v}" for k,v in parts))
PY
}
say ""; say "=== FIT prior gen1 (lambda=$PRIOR_VISIT) sur corpus tb-regen + combos ==="
concat "$W/corpus.jnnw" "$W/tbregen.jnnw" "$W/combos.jnnw" | tee -a "$RES"
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
  --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
  --prior-mean "$W/gen1_prior.pjtw" --prior-visit-scale "$PRIOR_VISIT" --prior-decay "$PRIOR_DECAY" \
  --out "$W/candtb.pjtw" >"$W/candtb.log" 2>&1 || { say "TRAIN FAIL"; tail -14 "$W/candtb.log"|sed 's/^/  /'; exit 9; }
rm -f "$W/feat"
grep -iE 'prior|train_loss' "$W/candtb.log" | tail -3 | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/candtb.pjtw" > "$ART/champion-tbregen.pjtw.gz"
commit_to_main "$ART/champion-tbregen.pjtw.gz" "$ARTREL/champion-tbregen.pjtw.gz" "tb-regen: commit champion-tbregen JOB-SIDE (fit prior gen1 sur corpus +tb-relabel)" \
  && say "  champion-tbregen committe job-side" || say "  ⚠ commit champion echoue"

# ---- JUGE moteur COIN par defaut (candidat + baselines dans le MEME build) ----
pjudge(){ local np="$1" rp="$2" tag="$3"
  for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$np" \
    --jass-b "$J" --pattern-b "$rp" --depth "$JUDGE_DEPTH" --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" \
    --quiet --openings-file "$DILF" >"$W/j_${tag}.$s" 2>&1 & done; wait
  python3 - "$tag" "$W"/j_${tag}.* <<'PY' 2>&1 | tee -a "$RES"
import sys,math; tag=sys.argv[1]; a=d=b=0
for f in sys.argv[2:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
  except: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; ex2=(a+0.25*d)/g if g else 0; v=ex2-r*r
se=math.sqrt(v/g) if g and v>0 else 0.5/(g**0.5 if g else 1); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="COMPOSE (borne basse IC>0.50)" if lo>0.50 else ("REGRESSE (hors-IC)" if hi<0.50 else "NEUTRE (IC contient 0.50)")
print(f"  [{tag}] games={g} A={a} B={b} D={d}  rate={r:.4f}+-{1.96*se:.4f}  elo~{elo:+.0f}  IC=[{lo:.4f},{hi:.4f}]  => {vd}")
PY
  rm -f "$W"/j_${tag}.* ; }
say ""; say "=== JUGE (moteur COIN par defaut, meme build des 2 cotes, d${JUDGE_DEPTH} dilf x${JUDGE_PAIRS}) ==="
pjudge "$W/candtb.pjtw" "$W/gen1.pjtw" "candtb-vs-gen1"
[ -s "$W/champregen.pjtw" ] && pjudge "$W/candtb.pjtw" "$W/champregen.pjtw" "candtb-vs-champregen"
say ""
say "  GATE (1) candtb-vs-gen1 : borne basse IC>0.50 => tb-relabel a debloque le plateau au scale (plain-regen etait"
say "     NEUTRE 0.5041 en 0570) => PROMO champion-tbregen (nouveau champion EVAL), chaine gen suivante."
say "  (2) candtb-vs-champregen : marge de tb-relabel au-dessus du plain regen (meme package, seul tb ajoute)."
say "  Sinon (NEUTRE/REGRESSE vs gen1) => tb-relabel gagne en iso-volume (0587) mais ne compose pas au scale avec prior"
say "     gen1 => diagnostiquer (dose tb en finale / prior ecrase le signal finale) avant de conclure."
commit_to_main "$RES" "$ARTREL/VERDICT.txt" "0589 tb-regen prod : verdict (gate candtb-vs-gen1 + marge vs champregen)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit verdict echoue"
say "=== fin manche prod tb-relabel ==="
