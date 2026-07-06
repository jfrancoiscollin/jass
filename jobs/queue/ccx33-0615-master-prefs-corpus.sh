#!/usr/bin/env bash
# id: ccx33-0615-master-prefs-corpus
# description: PISTE (a) BRAS M (Bonanza validé) — le bras S (auto-oracle d9) a échoué en G1 (semi-circulaire, survie 0.34->0.26
# quel que soit l'anchor, 0613). Le bras M utilise un oracle EXTERNE non-circulaire : le COUP JOUÉ par un maître (>=2000 Elo)
# = préféré ; toutes les sœurs légales = dominées. Pas de biais-de-nulles (on n'utilise PAS le résultat, seulement le coup).
# Pipeline : vérif expert_games.db -> extraction (parent + from/to du coup joué, coups QUIETS hors-book) -> gen-siblings
# --played-moves (match du coup parmi les enfants, src=MASTER) -> corpus de paires maîtres + manifest. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0615-master-prefs-corpus/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0615-master-prefs-corpus/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mpref5; rm -rf "$W"; mkdir -p "$W"
DB=/root/jass/data/expert_games.db
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
NPAR=100000; MIN_ELO=2000; SKIP_BOOK=8

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== BRAS M master-prefs — HEAD main $(git log --oneline -1|cat) ==="
[ -f "$DB" ] && say "  ✓ expert_games.db présent ($(du -h "$DB"|cut -f1))" || { say "  ❌ ABORT : $DB absent sur la box (0014 non persisté). Bras M nécessite un re-fetch."; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0614 : expert_games.db absent"; exit 0; }
say "  jeux >=${MIN_ELO} : $(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('SELECT COUNT(*) FROM expert_games WHERE white_rating>=$MIN_ELO AND black_rating>=$MIN_ELO AND pdn IS NOT NULL').fetchone()[0])" 2>&1)"

git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp; exit 6; }
J="$W/build/jass"; git checkout -- src/main.cpp 2>/dev/null || true

# ---- extraction : (parent record, from/to du coup joué) pour les plies QUIETS hors-book, >=MIN_ELO ----
say ""; say "=== extraction master (>= $NPAR parents, quiets, skip-book=$SKIP_BOOK) ==="
python3 - "$DB" "$J" "$W/parents.jnnw" "$W/moves.bin" "$NPAR" "$MIN_ELO" "$SKIP_BOOK" <<'PY' 2>&1 | tee -a "$RES"
import sqlite3,sys,struct,logging
sys.path.insert(0,'tools')
from pdn_to_jnnw import JassOracle, extract_moves, fen_to_bitboards, _strip_tags_and_comments, _REC_STRUCT
from pathlib import Path
db,jbin,outp,outm,N,mine,skip=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),int(sys.argv[6]),int(sys.argv[7])
logging.basicConfig(level=logging.ERROR); log=logging.getLogger('x')
conn=sqlite3.connect(db)
cur=conn.execute("SELECT pdn FROM expert_games WHERE white_rating>=? AND black_rating>=? AND pdn IS NOT NULL",(mine,mine))
orc=JassOracle(Path(jbin),log)
par=bytearray(); mov=bytearray(); npar=0; ngames=0; bad=0
for (pdn,) in cur:
    if npar>=N: break
    body=_strip_tags_and_comments(pdn or ""); moves=extract_moves(body)
    if not moves: continue
    orc.reset(); ngames+=1; okg=True
    for i,mv in enumerate(moves):
        try: fen=orc.fen()
        except Exception: okg=False; break
        if i>=skip and 'x' not in mv:
            try:
                stm,wm,wk,bm,bk=fen_to_bitboards(fen)
                parts=mv.replace('-',' ').replace('x',' ').split()
                frm=int(parts[0]); to=int(parts[1])
                if 1<=frm<=50 and 1<=to<=50:
                    par+=_REC_STRUCT.pack(wm,wk,bm,bk,stm,0,0); mov+=bytes([frm,to]); npar+=1
                    if npar>=N: break
            except Exception: bad+=1
        if not orc.apply(mv): okg=False; break
try: orc.close()
except Exception: pass
open(outp,'wb').write(b'JNNW'+struct.pack('<I',npar)+bytes(par))
open(outm,'wb').write(bytes(mov))
print(f"  extraction : {npar} parents (coups quiets) de {ngames} parties ; parse-fails={bad}")
PY
NPARENTS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])" 2>&1)
say "  parents.jnnw=$NPARENTS ; moves.bin=$(python3 -c "import os;print(os.path.getsize('$W/moves.bin')//2)" 2>&1)"
[ "$NPARENTS" -gt 1000 ] 2>/dev/null || { say "ABORT extraction vide"; exit 7; }

# ---- gen-siblings --played-moves : coup joué=préféré, sœurs=dominées (src=MASTER, sans recherche) ----
say ""; say "=== gen-siblings --played-moves (bras M) ==="
"$J" --gen-siblings "$W/parents.jnnw" "$W/mpairs.jnnw" 0 --played-moves "$W/moves.bin" --max-pairs-per-parent 16 >"$W/gs.log" 2>&1 || { say "GENSIB FAIL"; tail -5 "$W/gs.log"|sed 's/^/  /'; exit 8; }
grep -h '^GENSIB' "$W/gs.log" | sed 's/^/  /' | tee -a "$RES"
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/mpairs.jnnw','rb').read(8)[4:8])[0]//2)" 2>&1)
say "  master-pref paires : $NPAIRS"

gzip -c "$W/mpairs.jnnw" > "$ART/master-prefs.jnnw.gz"
commit_to_main "$ART/master-prefs.jnnw.gz" "$ARTREL/master-prefs.jnnw.gz" "bras M : corpus master-prefs ($NPAIRS paires, coups maîtres >=$MIN_ELO)" \
  && say "  corpus committe ($(du -h "$ART/master-prefs.jnnw.gz"|cut -f1))" || say "  ⚠ commit corpus echoue"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0614 bras M master-prefs corpus (oracle externe non-circulaire) — pret pour G1" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "  => next : G1 sur master-prefs (rank_finetune + survie) — l'oracle externe généralise-t-il là où le bras S a échoué ?"
say "=== fin bras M corpus ==="
