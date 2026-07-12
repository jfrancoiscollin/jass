#!/usr/bin/env bash
# id: cpx62-0681-adjud-p2p3-score
# description: MEMO PREDICATS §2/§5 pas 2 — note les 2 premiers prédicats (VETOS, zero risque) sur le harnais TB :
#   P3 = dame enfermee (veto de l'adjud materielle)  ;  P2 = blocage total (verdict DRAW).
# Composes depuis les primitives dilf, moteur = jass --dump-legal (DumpEngine, module pattern_jass/tools/adjud, sur develop).
# Sort, pour chaque predicat : PRECISION vs TB (admission >=99.9%) + FIRE-RATE + (P3) combien des faux-WIN |net|>=4 il vetote.
# Scorer 2 passes : filtre candidats cheap (sans moteur) -> dump-legal des candidats (2 variantes de trait) -> score moteur.
# n<plancher sur un sous-ensemble => INCONCLUANT sur CE predicat (jamais "neutre" sur du vide). Aucun bake, aucune boucle gen.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0681-adjud-p2p3-score/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0681-adjud-p2p3-score/artefacts"
W=/root/cw-adjp2p3; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # 8ter
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
APP=/root/egdb_extracted/app
DILF=/root/dilf-src
NPROBE=2000; NMAIN=150000; NMIN=20000; BUDGET_S=700
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
DFA=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== ADJUD P2/P3 SCORING (§2 harnais, vetos) — nproc=$NCPU df=${DFA}Mo ==="
[ "${DFA:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }

# --- pull src + module adjud de develop + arch_assert + build EGDB ---
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true; done
mkdir -p pattern_jass/tools/adjud
for f in __init__.py engine.py predicates.py; do
  git show "origin/develop:pattern_jass/tools/adjud/$f" > "pattern_jass/tools/adjud/$f" 2>/dev/null || { say "ABORT module adjud absent sur develop"; restore_src; exit 5; }; done
grep -q g_emasks src/scan_eval.cpp && grep -q has_any_capture src/search.cpp && grep -q run_dump_legal_mode src/main.cpp || { say "ABORT archi (dump-legal/opts absents)"; restore_src; exit 5; }
say "  garde-fou archi ✓ (dump-legal présent)"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0681 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"

[ -d "$APP" ] || { say "ABORT : DB egdb absente ($APP) sur cette box"; restore_src; exit 4; }
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null || true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF:/root/jass/pattern_jass/tools" python3 -c "import pedagogy.game, adjud.engine, adjud.predicates; print('IMPORTS_OK')" >"$W/imp.log" 2>&1
grep -q IMPORTS_OK "$W/imp.log" && say "  dilf+adjud imports ✓" || { say "ABORT imports"; cat "$W/imp.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 8; }

# --- micro-calib + echantillon TB uniforme ---
t0=$(date +%s); JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=1024 "$J" --gen-egdb-wld "$NPROBE" "$W/probe.jnnw" "$APP" 7 1024 1 >"$W/probe.log" 2>&1
dt=$(( $(date +%s)-t0 )); [ "$dt" -lt 1 ] && dt=1; RATE=$(( NPROBE/dt )); N=$(( RATE*BUDGET_S )); [ "$N" -gt "$NMAIN" ] && N="$NMAIN"; [ "$N" -lt "$NMIN" ] && N="$NMIN"
say "  rate≈${RATE} pos/s → N=$N"
JASS_EGDB_PATH="$APP" JASS_EGDB_CACHE_MB=2048 "$J" --gen-egdb-wld "$N" "$W/pool.jnnw" "$APP" 7 2048 12345 >"$W/gen.log" 2>&1 || { say "ABORT gen-egdb-wld"; tail -6 "$W/gen.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 7; }
tail -1 "$W/gen.log" | sed 's/^/  /' | tee -a "$RES"

# --- PASS 1 : filtre candidats (cheap, sans moteur) -> FENs des candidats (2 variantes de trait) ---
say ""; say "=== scoring P2/P3 vs TB ==="
PYTHONPATH="$DILF:/root/jass/pattern_jass/tools" JBIN="$J" WDIR="$W" python3 - "$W/pool.jnnw" "$NMIN" <<'PY' 2>&1 | tee -a "$RES"
import os,struct,sys,subprocess
from dataclasses import replace
from pedagogy.game import GameState, state_to_fen
from pedagogy.features.material import count_material, KING_VALUE
from adjud.engine import DumpEngine, parse_dump_line
from adjud.predicates import ahead_side, p2_blockage_draw, p3_trapped_king_veto

pool=sys.argv[1]; nmin=int(sys.argv[2]); J=os.environ["JBIN"]; W=os.environ["WDIR"]
d=open(pool,'rb').read(); assert d[:4]==b'JNNW'; n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]
def bits(x): return frozenset(s for s in range(1,51) if (x>>(s-1))&1)
recs=[]      # (state, wdl_stmPOV)
for i in range(n):
    r=body[i*REC:(i+1)*REC]
    if len(r)<REC: break
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]; wdl=struct.unpack('<b',r[37:38])[0]
    st=GameState(white_men=bits(wm),white_kings=bits(wk),black_men=bits(bm),black_kings=bits(bk),
                 turn=("white" if stm==0 else "black"))
    recs.append((st,wdl,stm))
tot=len(recs)
if tot<nmin: print(f"  ABORT/INCONCLUANT : n={tot} < {nmin}"); sys.exit(0)

# cheap candidate filters (no engine)
M=4                       # marge d'adjud materielle de reference (cf 0680)
def total_pieces(st): return len(st.white_men)+len(st.white_kings)+len(st.black_men)+len(st.black_kings)
p3_cand=[]; p2_cand=[]
for idx,(st,wdl,stm) in enumerate(recs):
    ah=ahead_side(st)
    if ah is not None and st.kings_of(ah) and abs(count_material(st)["balance"])>=M:
        p3_cand.append(idx)
    if not st.white_kings and not st.black_kings and total_pieces(st)<=8:
        p2_cand.append(idx)
cand=sorted(set(p3_cand)|set(p2_cand))
# dump-legal both turn variants for candidates
fenset=[]; idx2fen={}
for idx in cand:
    st=recs[idx][0]; wf=state_to_fen(replace(st,turn="white")); bf=state_to_fen(replace(st,turn="black"))
    idx2fen[idx]=(wf,bf); fenset.append(wf); fenset.append(bf)
uniq=list(dict.fromkeys(fenset))
open(f"{W}/dl.in","w").write("\n".join(uniq)+"\n")
subprocess.run([J,"--dump-legal",f"{W}/dl.in",f"{W}/dl.out"],check=True,stderr=subprocess.DEVNULL)
outs=[l.rstrip("\n") for l in open(f"{W}/dl.out")]
eng=DumpEngine()
for f,o in zip(uniq,outs): eng.add(f,o)

def win_for(side, wdl, stm):    # TB win for `side` ? wdl is stm-POV (+1 stm wins)
    stm_side="white" if stm==0 else "black"
    return (wdl==+1) if side==stm_side else (wdl==-1)

print(f"  echantillon n={tot} ; candidats P3={len(p3_cand)} P2={len(p2_cand)} (dump {len(uniq)} FEN)")

# ---- P3 veto : precision + recall sur les faux-WIN |net|>=4 avec dame ----
# faux-WIN@M4 (cible P3) = |net|>=4, ahead a une dame, TB PAS un win pour ahead
target=0; caught=0; fire=0; fire_correct=0
for idx in p3_cand:
    st,wdl,stm=recs[idx]; ah=ahead_side(st)
    isfalse = not win_for(ah,wdl,stm)
    if isfalse: target+=1
    try: v=p3_trapped_king_veto(st,eng,ah,margin=M)
    except KeyError: v=False
    if v:
        fire+=1
        if isfalse: fire_correct+=1;
        if isfalse: caught+=1
prec3 = 100*fire_correct/fire if fire else 0.0
rec3  = 100*caught/target if target else 0.0
if fire==0:
    print(f"  P3 veto: fire=0 sur {len(p3_cand)} candidats => INCONCLUANT (aucun tir ; assouplir margin/critere)")
else:
    print(f"  P3 veto (dame enfermee, margin={M}): fire={fire} PRECISION={prec3:.3f}%  (vetos justes={fire_correct})")
    print(f"           faux-WIN|net>=4-avec-dame ciblés={target}, attrapés={caught} => recall={rec3:.2f}%  [admission >=99.9%]")

# ---- P2 draw : precision + fire-rate, sweep max_mobility ----
for k in (1,2,3):
    fire=0; correct=0
    for idx in p2_cand:
        st,wdl,stm=recs[idx]
        try: v=p2_blockage_draw(st,eng,max_mobility=k)
        except KeyError: v=False
        if v:
            fire+=1
            if wdl==0: correct+=1
    if fire==0:
        print(f"  P2 draw (max_mob<={k}): fire=0 => INCONCLUANT")
    else:
        pr=100*correct/fire
        fr=100*fire/tot
        print(f"  P2 draw (max_mob<={k}): fire={fire} ({fr:.3f}% du pool) PRECISION={pr:.3f}%  (draws justes={correct})  [admission >=99.9%]")
print("  LECTURE : un predicat >=99.9% de precision est ADMIS comme cran de l'escalier ; sinon rejeté/raffiné.")
PY

say ""; say "=== fin adjud-p2p3-score ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0681 adjud-p2p3-score FIN : P3 veto + P2 draw notés vs TB (voir precision/fire)" && say "  RESULTS committé ✓" || say "  ⚠ commit RESULTS"
restore_src
