#!/usr/bin/env bash
# id: ccx33-0624-mmto-maitres-v3-highvol
# description: MMTO v3 HAUT-VOLUME (« mieux nourrie », idée JFC). 0621 sous-nourri : 30k parents / 282k paires (vs 100k/414k
# au static) ET les feuilles-PV s'étalent sur plus de buckets → support fin → fit +0.0014 dominé par l'anchor. Ici 100k
# parents maîtres (3.3×, ~940k paires feuilles), gen-siblings --leaf-mode --nnue gen1, fit --leaf-pov sweep anchor {0.05,0.1}
# (anchor plus faible = laisse le fit s'exprimer ; sûr car objectif à-travers-recherche correct, POV fixé 0621). Candidats
# committés pour A/B Elo haut-N vs gen1. Si le gain généraliste (+33, 0622) s'amplifie avec le volume → marge réelle → boucle
# externe. Si toujours plat → le search capte déjà tout. Committe parents+moves 100k (réutilisables). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0624-mmto-maitres-v3-highvol/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0624-mmto-maitres-v3-highvol/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmto3; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-mmto3
DB=/root/jass/data/expert_games.db
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NPAR=100000; MIN_ELO=2000; SKIP_BOOK=8; LEAFD=5; MAXPP=16; LAM=0.3; WSOFF=-1000000000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== MMTO v1 maîtres — HEAD main $(git log --oneline -1|cat) ==="
[ -f "$DB" ] && say "  ✓ expert_games.db ($(du -h "$DB"|cut -f1))" || { say "  ❌ ABORT : $DB absent"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0620 ABORT db absente"; exit 5; }

# ---- build jass (develop : --leaf-mode) + rank_finetune (develop) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
say "  ✓ build develop OK ; NUM_PATTERNS=$NP"

# ---- extraction maîtres : (parent record, from/to du coup joué), quiets hors-book ----
say ""; say "=== extraction maîtres (>= $NPAR parents, quiets, skip-book=$SKIP_BOOK, elo>=$MIN_ELO) ==="
python3 - "$DB" "$J" "$W/parents.jnnw" "$W/moves.bin" "$NPAR" "$MIN_ELO" "$SKIP_BOOK" <<'PY' 2>&1 | tee -a "$RES"
import sqlite3,sys,struct,logging
sys.path.insert(0,'tools')
from pdn_to_jnnw import JassOracle, extract_moves, fen_to_bitboards, _strip_tags_and_comments, _REC_STRUCT
from pathlib import Path
db,jbin,outp,outm,N,mine,skip=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),int(sys.argv[6]),int(sys.argv[7])
logging.basicConfig(level=logging.ERROR); log=logging.getLogger('x')
conn=sqlite3.connect(db)
cur=conn.execute("SELECT pdn FROM expert_games WHERE white_rating>=? AND black_rating>=? AND pdn IS NOT NULL",(mine,mine))
orc=JassOracle(Path(jbin),log); par=bytearray(); mov=bytearray(); npar=0; ngames=0; bad=0
for (pdn,) in cur:
    if npar>=N: break
    body=_strip_tags_and_comments(pdn or ""); moves=extract_moves(body)
    if not moves: continue
    orc.reset(); ngames+=1
    for i,mv in enumerate(moves):
        try: fen=orc.fen()
        except Exception: break
        if i>=skip and 'x' not in mv:
            try:
                stm,wm,wk,bm,bk=fen_to_bitboards(fen)
                parts=mv.replace('-',' ').replace('x',' ').split(); frm=int(parts[0]); to=int(parts[1])
                if 1<=frm<=50 and 1<=to<=50:
                    par+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); mov+=bytes([frm,to]); npar+=1
                    if npar>=N: break
            except Exception: bad+=1
        if not orc.apply(mv): break
try: orc.close()
except Exception: pass
open(outp,'wb').write(b'JNNW'+struct.pack('<I',npar)+bytes(par)); open(outm,'wb').write(bytes(mov))
print(f"  extraction : {npar} parents de {ngames} parties ; parse-fails={bad}")
PY
NPARENTS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])" 2>&1)
say "  parents=$NPARENTS ; moves=$(python3 -c "import os;print(os.path.getsize('$W/moves.bin')//2)")"
[ "$NPARENTS" -gt 1000 ] 2>/dev/null || { say "ABORT extraction vide"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
# commit parents+moves (réutilisables pour la boucle externe 0622)
gzip -c "$W/parents.jnnw" > "$ART/maitres-parents.jnnw.gz"; gzip -c "$W/moves.bin" > "$ART/maitres-moves.bin.gz"
commit_to_main "$ART/maitres-parents.jnnw.gz" "$ARTREL/maitres-parents.jnnw.gz" "0624 maîtres parents 100k ($NPARENTS, réutilisable MMTO)" >/dev/null 2>&1 || true
commit_to_main "$ART/maitres-moves.bin.gz" "$ARTREL/maitres-moves.bin.gz" "0624 maîtres moves 100k (aligné parents)" >/dev/null 2>&1 || true

# ---- split parents+moves en NCPU shards alignés (gen-siblings est mono-thread) ----
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi:
        open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC])
    open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
print(f"  split : {nc} shards (~{per} parents/shard)")
PY

# ---- MMTO gen : gen-siblings --leaf-mode --nnue gen1 (feuilles-PV depuis le champion), filtre WS off ----
say ""; say "=== MMTO gen-siblings --leaf-mode (depth=$LEAFD, --nnue gen1, WS off = même support que 0619) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WSOFF" --nnue "$W/gen1.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
grep -h '^GENSIB' "$W"/gs_*.log | sed 's/^/  /' | tee -a "$RES" | tail -2
# concat pairs (records consécutifs 2k/2k+1 préservés par shard)
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  MMTO pairs concat : {tot} records ({tot//2} paires)")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  MMTO paires (feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT pas assez de paires MMTO"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 8; }

# ---- dump features des feuilles + fit rank_finetune {0.1,0.3} ancré à gen1 ----
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 9; }
say "  dump-eval-features : $(tail -1 "$W/dump.log")"
OKA=""
for A in 0.05 0.1; do
  say ""; say "=== rank_finetune MMTO anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/mmto_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"
    gzip -c "$W/mmto_$A.pjtw" > "$ART/mmto3_$A.pjtw.gz"
    commit_to_main "$ART/mmto3_$A.pjtw.gz" "$ARTREL/mmto3_$A.pjtw.gz" "0624 candidat MMTO v3 haut-volume anchor=$A (100k parents, feuilles-PV d$LEAFD, --leaf-pov)" \
      && say "  [$A] candidat MMTO committé" || say "  [$A] ⚠ commit echoue"
  else say "  [$A] ABORT (gate) : $(tail -1 "$W/ft_$A.log")"; fi
done
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null || true

say ""
say "  => next : A/B Elo haut-N mmto3_{0.05,0.1} vs gen1 (harnais 0619)."
say "  LECTURE : MMTO bat gen1 hors-IC (là où statique=−847) => la MÉTHODE (statique) était le verrou => boucle externe 0622."
say "            MMTO échoue aussi => l'éval linéaire n'exploite pas l'ordre maître même à travers la recherche => marge close."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0624 MMTO v3 haut-volume (100k parents, --leaf-pov) : candidats prets pour A/B" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin MMTO v1 ==="
