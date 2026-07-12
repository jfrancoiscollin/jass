#!/usr/bin/env bash
# id: cpx62-0687-pcblues-prefs-finetune
# description: PC BLUES PREFS FINETUNE (go JFC "Go B" 2026-07-12). Le corpus PC Blues raffiné par dilf fournit 5665
# préférences POSITIVES certifiées (!/!! annotés par Piens/Boom/Groeneveld — le prof humain élite, vue externe comme 0464)
# sur des positions vérifiées par re-jeu FMJD. Ici : parents = positions des coups !/!! (quiets hors-prise, comme 0624),
# gen-siblings --leaf-mode --nnue gen2-mmto (feuilles-PV d5) -> paires (joué ≻ sibling), fit rank_finetune ancré
# {0.05,0.1} sur gen2-mmto. Candidats committés pour A/B ensuite (job séparé, pattern 0624). PRÉ-ESTIMATION (ancre 0624 :
# 100k parents ≈ 5-15 min gen+fit) : ~6k parents -> ~10-20 min TOTAL cpx62. Négatives ?/?? = phase 2 (inversion de
# préférence, différée). Source données : branche claude/pcblues-corpus-extraction-2i92bj (data/pcblues_prefs_graded.tsv).
# AUCUN NNUE (adaptateur linéaire seulement).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0687-pcblues-prefs-finetune/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0687-pcblues-prefs-finetune/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-pcbprefs; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-pcbprefs
CHAMP_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LEAFD=5; MAXPP=16; LAM=0.3; WSOFF=-1000000000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== 0687 PC Blues prefs finetune — HEAD main $(git log --oneline -1|cat) ==="

# ---- données : TSV prefs depuis la branche source dilf/jass ----
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
git show "origin/$SRC_BRANCH:data/pcblues_prefs_graded.tsv" > "$W/prefs.tsv" \
  || { say "ABORT: prefs TSV absent de origin/$SRC_BRANCH"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0687 ABORT tsv absent"; exit 4; }
say "  ✓ prefs.tsv : $(grep -cv '^#' "$W/prefs.tsv") lignes"

# ---- build jass (develop : --gen-siblings/--leaf-mode) + rank_finetune (develop) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT champion gen2-mmto"; restore_src; exit 4; }
say "  ✓ build develop OK ; NUM_PATTERNS=$NP ; anchor = gen2-mmto"

# ---- parents = positions des coups !/!! (quiets hors-prise, pattern 0624) ----
say ""; say "=== parents depuis prefs !/!! (quiets ; captures skippées, notées) ==="
python3 - "$W/prefs.tsv" "$W/parents.jnnw" "$W/moves.bin" <<'PY' 2>&1 | tee -a "$RES"
import sys,struct
sys.path.insert(0,'tools')
from pdn_to_jnnw import fen_to_bitboards, _REC_STRUCT
tsv,outp,outm=sys.argv[1],sys.argv[2],sys.argv[3]
par=bytearray(); mov=bytearray(); n=0; ncap=0; nneg=0; nbad=0
for ln in open(tsv,encoding='utf-8'):
    if ln.startswith('#') or not ln.strip(): continue
    try: fen,move,grade,_src=ln.rstrip('\n').split('\t')
    except ValueError: nbad+=1; continue
    if grade not in ('!','!!'): nneg+=1; continue
    if 'x' in move: ncap+=1; continue
    try:
        stm,wm,wk,bm,bk=fen_to_bitboards(fen)
        frm,to=(int(x) for x in move.split('-'))
        if not (1<=frm<=50 and 1<=to<=50): nbad+=1; continue
    except Exception: nbad+=1; continue
    par+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); mov+=bytes([frm,to]); n+=1
open(outp,'wb').write(b'JNNW'+struct.pack('<I',n)+bytes(par)); open(outm,'wb').write(bytes(mov))
print(f"  parents={n} (captures skippées={ncap}, négatives différées={nneg}, invalides={nbad})")
PY
NPARENTS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
[ "$NPARENTS" -gt 500 ] 2>/dev/null || { say "ABORT parents insuffisants ($NPARENTS)"; restore_src; exit 7; }

# ---- shards alignés (gen-siblings mono-thread) ----
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

# ---- gen-siblings --leaf-mode (feuilles-PV depuis gen2-mmto) ----
say ""; say "=== gen-siblings --leaf-mode (d=$LEAFD, --nnue gen2-mmto, WS off) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WSOFF" --nnue "$W/champ.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
grep -h '^GENSIB' "$W"/gs_*.log | sed 's/^/  /' | tee -a "$RES" | tail -2
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  pairs concat : {tot} records ({tot//2} paires)")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  paires (joué-!/!! ≻ sibling, feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 500 ] 2>/dev/null || { say "ABORT paires insuffisantes"; restore_src; exit 8; }

# ---- dump features + fit ancré gen2-mmto {0.05, 0.1} ----
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; restore_src; exit 9; }
say "  dump-eval-features : $(tail -1 "$W/dump.log")"
for A in 0.05 0.1; do
  say ""; say "=== rank_finetune pcblues-prefs anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/champ.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/pcb_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"
    gzip -c "$W/pcb_$A.pjtw" > "$ART/pcbprefs_$A.pjtw.gz"
    commit_to_main "$ART/pcbprefs_$A.pjtw.gz" "$ARTREL/pcbprefs_$A.pjtw.gz" \
      "0687 candidat pcblues-prefs anchor=$A ($NPARENTS parents !/!!, feuilles-PV d$LEAFD, ancre gen2-mmto)" \
      && say "  [$A] candidat committé" || say "  [$A] ⚠ commit echoue"
  else say "  [$A] FIT FAIL : $(tail -1 "$W/ft_$A.log")"; fi
done
restore_src

say ""
say "  => next : A/B Elo pcbprefs_{0.05,0.1} vs gen2-mmto (mt0.2, sizing léger, à valider JFC)."
say "  LECTURE : hors-IC positif => le prof humain élite (!/!!) ajoute au-delà de gen2-mmto (là où Scan-d14 = PERD, 0672)."
say "            plat/négatif => le signal !/!! est déjà capté par la recherche ; passer aux NÉGATIVES ?/?? (phase 2)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0687 pcblues-prefs : gen+fit termines, candidats prets pour A/B" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin 0687 ==="
