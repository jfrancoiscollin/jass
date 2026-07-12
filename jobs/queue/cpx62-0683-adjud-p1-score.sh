#!/usr/bin/env bash
# id: cpx62-0683-adjud-p1-score
# description: MEMO CURRICULUM A4 — note P1 (PERCEE IMPRENABLE -> verdict WIN) sur le harnais TB. P1 = la seule famille "verdict"
# prometteuse (course geometrique hors-TB) ; ce job DECIDE si le programme predicats a un etage "verdicts" ou seulement "vetos".
# Composé depuis dilf (promotion_distance + threatened_captures via --dump-legal/DumpEngine). Teste P1 pour LES DEUX camps
# (une percee gagne meme a materiel egal). Sort : PRECISION (WIN) vs TB (admission >=99.9%) + fire-rate + couverture du set WIN,
# sweep max_d in {2,3,4}. n<plancher => ABORT ; fire=0 sur un md => INCONCLUANT (jamais "neutre"). Aucun bake.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0683-adjud-p1-score/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0683-adjud-p1-score/artefacts"
W=/root/cw-adjp1; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
APP=/root/egdb_extracted/app
DILF=/root/dilf-src
NPROBE=2000; NMAIN=200000; NMIN=30000; BUDGET_S=750
START=$(date +%s)

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp 2>/dev/null||true; }

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== ADJUD P1 SCORING (percee->WIN) — nproc=$NCPU df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true; done
mkdir -p pattern_jass/tools/adjud
for f in __init__.py engine.py predicates.py; do
  git show "origin/develop:pattern_jass/tools/adjud/$f" > "pattern_jass/tools/adjud/$f" 2>/dev/null || { say "ABORT module adjud"; restore_src; exit 5; }; done
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q run_dump_legal_mode src/main.cpp && grep -q p1_runaway_win pattern_jass/tools/adjud/predicates.py || { say "ABORT archi (dump-legal/P1 absents)"; restore_src; exit 5; }
say "  garde-fou archi ✓ (dump-legal + P1)"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0683 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
[ -d "$APP" ] || { say "ABORT DB egdb absente ($APP)"; restore_src; exit 4; }
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null || true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF:/root/jass/pattern_jass/tools" python3 -c "import adjud.predicates; print('OK')" >"$W/imp.log" 2>&1
grep -q OK "$W/imp.log" && say "  dilf+adjud imports ✓" || { say "ABORT imports"; cat "$W/imp.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 8; }

t0=$(date +%s); JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=1024 "$J" --gen-egdb-wld "$NPROBE" "$W/probe.jnnw" "$APP" 7 1024 1 >"$W/probe.log" 2>&1
dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1; RATE=$(( NPROBE/dt )); N=$(( RATE*BUDGET_S )); [ "$N" -gt "$NMAIN" ] && N="$NMAIN"; [ "$N" -lt "$NMIN" ] && N="$NMIN"
say "  rate≈${RATE} pos/s → N=$N"
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=2048 "$J" --gen-egdb-wld "$N" "$W/pool.jnnw" "$APP" 7 2048 12345 >"$W/gen.log" 2>&1 || { say "ABORT gen"; tail -6 "$W/gen.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 7; }
tail -1 "$W/gen.log" | sed 's/^/  /' | tee -a "$RES"

say ""; say "=== notation P1 (percee->WIN) vs TB, les 2 camps, sweep max_d ==="
PYTHONPATH="$DILF:/root/jass/pattern_jass/tools" JBIN="$J" WDIR="$W" python3 - "$W/pool.jnnw" "$NMIN" <<'PY' 2>&1 | tee -a "$RES"
import os,struct,sys,subprocess
from dataclasses import replace
from pedagogy.game import GameState, state_to_fen
from pedagogy.features.geometry import promotion_distance
from adjud.engine import DumpEngine
from adjud.predicates import p1_runaway_win
pool=sys.argv[1]; nmin=int(sys.argv[2]); J=os.environ["JBIN"]; W=os.environ["WDIR"]
d=open(pool,'rb').read(); assert d[:4]==b'JNNW'; n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]
def bits(x): return frozenset(s for s in range(1,51) if (x>>(s-1))&1)
recs=[]
for i in range(n):
    r=body[i*REC:(i+1)*REC]
    if len(r)<REC: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]; wdl=struct.unpack('<b',r[37:38])[0]
    recs.append((GameState(white_men=bits(wm),white_kings=bits(wk),black_men=bits(bm),black_kings=bits(bk),
                 turn=("white" if stm==0 else "black")),wdl,stm))
tot=len(recs)
if tot<nmin: print(f"  ABORT/INCONCLUANT : n={tot} < {nmin}"); sys.exit(0)
MAXD=4
def side_wins(side,wdl,stm):
    ss="white" if stm==0 else "black"; return (wdl==1) if side==ss else (wdl==-1)
# cheap candidate : for a side, defender has no king AND side has a man with promotion_distance<=MAXD
cand=[]   # (idx, side)
for idx,(st,wdl,stm) in enumerate(recs):
    for side in ("white","black"):
        deff="black" if side=="white" else "white"
        if st.kings_of(deff): continue
        men = st.white_men if side=="white" else st.black_men
        if any(promotion_distance(m,side)<=MAXD for m in men):
            cand.append((idx,side))
# dump both turn variants for candidate positions
fenset=[]
for idx,_ in cand:
    st=recs[idx][0]; fenset+=[state_to_fen(replace(st,turn="white")),state_to_fen(replace(st,turn="black"))]
uniq=list(dict.fromkeys(fenset)); open(f"{W}/dl.in","w").write("\n".join(uniq)+"\n")
subprocess.run([J,"--dump-legal",f"{W}/dl.in",f"{W}/dl.out"],check=True,stderr=subprocess.DEVNULL)
eng=DumpEngine()
for f,o in zip(uniq,[l.rstrip("\n") for l in open(f"{W}/dl.out")]): eng.add(f,o)
decisive=sum(1 for st,wdl,stm in recs if wdl!=0)
print(f"  n={tot} (decisive={decisive})  candidats (pos,side)={len(cand)}  dump={len(uniq)} FEN")
for md in (2,3,4):
    fire=correct=0
    for idx,side in cand:
        st,wdl,stm=recs[idx]
        try: v=p1_runaway_win(st,eng,side,max_d=md)
        except KeyError: v=False
        if v:
            fire+=1
            if side_wins(side,wdl,stm): correct+=1
    if fire==0:
        print(f"  P1 (max_d<={md}): fire=0 => INCONCLUANT")
    else:
        prec=100*correct/fire; fr=100*fire/tot; cov=100*correct/decisive if decisive else 0
        print(f"  P1 (max_d<={md}): fire={fire} ({fr:.3f}% du pool) PRECISION(WIN)={prec:.3f}%  cov(win-set)={cov:.2f}%  (justes={correct})  [admission >=99.9%]")
print("  LECTURE : P1>=99.9% => l'escalier a un ETAGE VERDICTS (adjudique des WIN hors-TB) ; sinon predicats=vetos seulement.")
PY

say ""; say "=== fin adjud-p1-score ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0683 adjud-p1-score FIN : P1 percee notée vs TB (decide l'étage verdicts)" && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
restore_src
