#!/usr/bin/env bash
# id: cpx62-0566-regen-mix-oncoin
# description: RE-GEN sur le NOUVEAU DEFAUT BAKE (coin corner+nmp, commit 4bda84da7, +49 Elo movetime) — boucle vertueuse
# re-armee (plan JFC). Le self-play est joue avec la recherche AMELIOREE (coin auto-inclus via le build main) + threat_ext
# (baké) => pilote plus fort => punit des tactiques que gen1 ne voyait pas => labels WDL meilleurs. Teste EMPIRIQUEMENT la
# fourche eval : si le champion issu de ces labels COMPOSE (bat gen1) => la marge etait LABELS/search, la boucle est vivante,
# on chaine ; sinon => CAPACITE => DOE feature-group. MIX 60% pd8 (1.2M) + 20% pd9 (400k) + 20% pd10 (400k) = 2M. Pilote=gen1,
# asym punisher conserve, quiet-only, combo-seed. GEN-ONLY (fit = job suivant, prior gen1, juge vs gen1). Infra : progress/
# checkpoints NUMEROTES + corpus committe JOB-SIDE par phase (un kill ne perd que la phase en cours). AUCUN NNUE. ~4-6h.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0566-regen-mix-oncoin/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-regenmix; rm -rf "$W"; mkdir -p "$W"
LABEL_DEPTH=4; OPEN_PLIES=8; EXPLORE_EPS=5; MAXPLIES=200
FORCE_SPEC="ext_forcing=1,forcing_ext_cap=6"; SEED_FRAC=25
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
SHARD_GLOB="jobs/results/ccx33-0438-lidraughts-fetch/artefacts/lidraughts-*.jnnw.gz"
ARTREL="jobs/results/cpx62-0566-regen-mix-oncoin/artefacts"

say "=== build jass depuis main (ARCHI COMPLETE + COIN BAKE : probcut5/lmr2/multicut4/nmp-finale) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
say "  HEAD main : $(git log --oneline -1 | cat)"
say "  confirme coin actif : $(git show origin/main:src/search_params.hpp | grep -cE 'probcut_min_depth = 5|lmr_first_full_nonpv = 2|multicut_min_depth = 4|eg_no_nmp  = false')/4 params-cle"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*5)); done; return 1; }
merge_into(){ local out="$1"; shift; python3 - "$out" "$@" <<'PY'
import struct,glob,sys
out=sys.argv[1]; pats=sys.argv[2:]; REC=38; body=b""; tot=0
files=[]
for p in pats: files+=sorted(glob.glob(p))
for f in files:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}
count_pos(){ python3 -c "import glob,os
t=0
for f in glob.glob('$1'):
    try: t+=max(0,(os.path.getsize(f)-8)//38)
    except: pass
print(t)" 2>/dev/null || echo 0; }
gen_phase(){ local pd="$1" nn="$2" tag="$3"; local per=$(( (nn+NCPU-1)/NCPU )); local pids=()
  say ""; say "=== PHASE $tag : ${nn} pos @ pd${pd} (x$NCPU shards, recherche=coin bake) ==="
  for s in $(seq 1 "$NCPU"); do "$J" --gen-data-wdl "$per" "$W/${tag}.jnnw.$s" "$LABEL_DEPTH" "$pd" "$MAXPLIES" "$((RANDOM*RANDOM+s))" \
      --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE_SPEC" --quiet-only \
      --seed-file "$SEEDFILE" --seed-frac "$SEED_FRAC" --random-open-plies "$OPEN_PLIES" --explore-eps "$EXPLORE_EPS" \
      >/dev/null 2>&1 & pids+=($!); done
  ( T0=$SECONDS; CY=0; while kill -0 "${pids[0]}" 2>/dev/null; do
      sleep 300; CY=$((CY+1))
      P=$(count_pos "$W/${tag}.jnnw.*"); DT=$((SECONDS-T0)); R=$(( P/(DT>0?DT:1) ))
      printf '%s [%s] positions~%s/%s debit~%s/s\n' "$(date -u +%H:%M:%SZ)" "$tag" "$P" "$nn" "$R" > "$ART/progress-${tag}-$(printf %03d $CY).txt"
    done ) & local MON=$!
  wait "${pids[@]}"; kill "$MON" 2>/dev/null || true; wait "$MON" 2>/dev/null || true
  local NP; NP=$(merge_into "$W/${tag}.jnnw" "$W/${tag}.jnnw.*")
  rm -f "$W/${tag}.jnnw."[0-9]*
  say "  phase $tag : ${NP} pos"
  gzip -c "$W/${tag}.jnnw" > "$ART/phase-${tag}.jnnw.gz"
  commit_to_main "$ART/phase-${tag}.jnnw.gz" "$ARTREL/phase-${tag}.jnnw.gz" "regen-mix: phase $tag committee (${NP} pos, coin bake)" \
    && say "  phase $tag committee job-side" || say "  (commit phase $tag echoue, restera au finalize)"
}

# seed-file (dilf + lidraughts mids)
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

# ---- MIX 60/20/20 : pd8 1.2M, pd9 400k, pd10 400k (self-play joue avec le coin bake) ----
gen_phase 8 1200000 "pd8"
gen_phase 9 400000  "pd9"
gen_phase 10 400000 "pd10"

say ""; say "=== MERGE final : corpus-regen-mix2M (60/20/20 pd8/9/10, recherche=coin bake, pilote gen1) ==="
NTOT=$(merge_into "$W/regenmix.jnnw" "$W/pd8.jnnw" "$W/pd9.jnnw" "$W/pd10.jnnw")
say "  total : ${NTOT} pos"
gzip -c "$W/regenmix.jnnw" > "$ART/corpus-regen-mix2M.jnnw.gz"
commit_to_main "$ART/corpus-regen-mix2M.jnnw.gz" "$ARTREL/corpus-regen-mix2M.jnnw.gz" "regen-mix: corpus 60/20/20 pd8/9/10 sur coin bake complet (${NTOT} pos)" \
  && say "  corpus committe JOB-SIDE ($(du -h "$ART/corpus-regen-mix2M.jnnw.gz"|cut -f1))" || say "  (commit final echoue, restera au finalize)"
say "  => PRET pour le FIT (prior gen1, juge vs gen1 dans le meme build coin => mesure pure de l'eval)."
say "=== fin regen-mix on coin ==="
