#!/usr/bin/env bash
# id: cpx62-0706-p1-runaway-harness
# description: HARNAIS NOTATION P1-PERCÉE (dernier candidat de l'etage verdicts, go JFC 2026-07-13). Apres la mort de
# P2 (0701 : blocage_structurel prec 5,26% ≤7p — un test STATIQUE ne monte pas a 99,9%), P1 echappe au theoreme : la
# percee n'est pas une propriete statique subtile, c'est une COURSE DE TEMPI calculee EXACTEMENT (run droit + intercept
# ≤ d tempi, BFS borne — deja code : adjud/predicates.py::p1_runaway_win). Le predicat ADJUGE WIN pour le camp qui a la
# percee imprenable. GATE GRAVE : quand il FIRE, le camp designe doit GAGNER ≥ 99,9% (sinon la percee ment). Pipeline :
# (1) self-play gen2 endgames (min-pieces 4, max-plies 200) -> positions ; (2) p1_runaway_win teste les DEUX camps ->
# FIRES (side enregistre) ; (3) arbitre = "le budget dit vrai" : ≤7p egdb-relabel EXACT (LE GATE), >7p deep-relabel d14
# +egdb (arbitre-d14-au-cap, exact si TB atteignable sinon signe d14) ; (4) precision = P(WIN-pour-le-camp | fire).
# Fire-targeting : gen ENDGAMES (min-pieces 4) car P1 fire dans les finales de pions -> fires majoritairement ≤7p =>
# TB-exact (repare la sous-puissance 0701 n=19). Build JASS_EGDB=ON, dilf clone. Robustesse 12-pts. AUCUN NNUE.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0706.lock
if ! flock -n 9; then echo "ABORT 0706 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0706-p1-runaway-harness/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0706-p1-runaway-harness/artefacts"
W=/root/cw-p1run
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=/root/dilf-src
PERG=12000; MAXPLIES=200; MINPIECES=4; STRONG_D=8; WEAK_D=3; JITTER=1; SKIP=8; DRAWFRAC=1.0; SEED=70400
ARB_DEPTH=14; SHARD_TIMEOUT=3600; MAXD=3

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys,re
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*"),key=lambda p:int(re.search(r"\.(\d+)$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}

say "=== harnais P1-percée — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
mkdir -p pattern_jass/tools/adjud   # main n'a pas ce dir (module sur develop) -> sans mkdir la redirection echoue silencieusement (bug 0704)
for f in pattern_jass/tools/adjud/__init__.py pattern_jass/tools/adjud/predicates.py pattern_jass/tools/adjud/engine.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
restore_src(){ git checkout -- src pattern_jass/src tools/scan_selfplay_gen.py pattern_jass/tools/adjud 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp && grep -q "has_any_capture" src/search.cpp || { say "ABORT archi"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"   # cpx62 : egdb sous /root/egdb_extracted (ceinture-bretelles runtime)
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 ABORT build"; exit 6; }
J="$W/build/jass"
[ -s pattern_jass/tools/adjud/predicates.py ] || { say "ABORT: pull adjud/predicates.py a echoue (dir manquant?)"; restore_src; exit 5; }
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null||true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF:pattern_jass/tools" python3 -c "from adjud.predicates import p1_runaway_win, ahead_side; from pedagogy.game import GameState; from scripts.pcblues.rules import RulesEngine; print('p1 import OK')" >"$W/imp.log" 2>&1 \
  || { say "ABORT import p1/dilf : $(cat "$W/imp.log"|tail -2)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 ABORT p1 import"; exit 7; }
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build egdb + p1 import OK ; egdb=$EGDIR"

# --- self-play gen2 endgames (min-pieces 4 -> finales de pions ou P1 fire) ---
say ""; say "=== self-play gen2 ${PERG}×${NCPU} (max-plies $MAXPLIES, min-pieces $MINPIECES = fire-targeting endgames) ==="
pids=()
for s in $(seq 0 $((NCPU-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/gen2.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$s" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" \
    --sample-every 1 --depth "$STRONG_D" --weak-depth "$WEAK_D" --depth-jitter "$JITTER" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" --seed "$SEED" --nshards "$NCPU" --shard "$s" >"$W/sp-$s.log" 2>&1 &
  pids+=($!)
done
wait "${pids[@]}"; restore_src
NP=$(merge_jnnw "$W/pos.jnnw" "$W/sp"); say "  positions générées : $NP"

# --- p1_runaway_win teste les DEUX camps -> FIRES (side enregistre, split ≤7p / >7p) ---
say ""; say "=== prédicat p1_runaway_win (adjud/predicates, max_d=$MAXD) — teste white ET black -> fires ==="
PYTHONPATH="$DILF:pattern_jass/tools" MAXD="$MAXD" python3 - "$W/pos.jnnw" "$W/fires7.jnnw" "$W/ahead7.txt" "$W/firesBig.jnnw" "$W/aheadBig.txt" <<'PY' | tee -a "$RES"
import struct,sys,os
from pedagogy.game import GameState
from scripts.pcblues.rules import RulesEngine
from adjud.predicates import p1_runaway_win
ENG=RulesEngine(); REC=38; MAXD=int(os.environ.get("MAXD","3"))
pos,out7,ah7,outbig,ahbig=sys.argv[1:6]
b=open(pos,'rb').read(); n=struct.unpack('<I',b[4:8])[0]
def sqs(v): return frozenset(s for s in range(1,51) if (v>>(s-1))&1)
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
rec7=[]; ah7l=[]; big=[]; ahbl=[]; tested=0; fires=0; seen=set()
for i in range(n):
    off=8+i*REC; wm,wk,bm,bk,stm=struct.unpack_from('<QQQQB',b,off)
    key=(wm,wk,bm,bk,stm)
    if key in seen: continue
    seen.add(key); tested+=1
    st=GameState(white_men=sqs(wm),white_kings=sqs(wk),black_men=sqs(bm),black_kings=sqs(bk),
                 turn='white' if stm==0 else 'black')
    side=None
    for cand in ('white','black'):                 # percee imprenable pour l'UN des deux camps
        try:
            if p1_runaway_win(st,ENG,cand,max_d=MAXD): side=cand; break
        except Exception: pass
    if side is None: continue
    fires+=1; tag='w' if side=='white' else 'b'
    if pc(wm)+pc(wk)+pc(bm)+pc(bk)<=7: rec7.append(b[off:off+REC]); ah7l.append(tag)
    else: big.append(b[off:off+REC]); ahbl.append(tag)
open(out7,'wb').write(b'JNNW'+struct.pack('<I',len(rec7))+b''.join(rec7))
open(outbig,'wb').write(b'JNNW'+struct.pack('<I',len(big))+b''.join(big))
open(ah7,'w').write("".join(ah7l)); open(ahbig,'w').write("".join(ahbl))
print(f"  positions testées (dédup) : {tested}")
print(f"  FIRES p1_runaway_win : {fires}  (≤7p={len(rec7)}  >7p={len(big)})")
PY
N7=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/fires7.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0)
NBIG=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/firesBig.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0)
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 fires : 7p=$N7 big=$NBIG" >/dev/null 2>&1 || true

# --- arbitre ≤7p : egdb-relabel EXACT (LE GATE) ---
if [ "$N7" -gt 0 ] 2>/dev/null; then
  "$J" --egdb-relabel "$W/fires7.jnnw" "$EGDIR" "$W/fires7_rel.jnnw" 2048 >"$W/rel7.log" 2>&1 || say "  (egdb-relabel warn)"
fi
# --- arbitre >7p : deep-relabel d14 + egdb (arbitre-d14-au-cap, "le budget dit vrai") ---
if [ "$NBIG" -gt 0 ] 2>/dev/null; then
  "$J" --deep-relabel "$W/firesBig.jnnw" "$W/firesBig_rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/relBig.log" 2>&1 || say "  (deep-relabel warn)"
fi

# --- precision = P(WIN-pour-le-camp-designe | fire) ---
python3 - "$W/fires7_rel.jnnw" "$W/ahead7.txt" "$W/firesBig_rel.jnnw" "$W/aheadBig.txt" "$N7" "$NBIG" <<'PY' | tee -a "$RES"
import struct,sys,os
def load(jnnw,ahfile):
    if not os.path.exists(jnnw) or not os.path.exists(ahfile): return (0,0,0,0)
    b=open(jnnw,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; ah=open(ahfile).read()
    corr=draw=wrong=0
    for i in range(n):
        off=8+i*38; stm=b[off+32]; wdl=struct.unpack_from('<b',b,off+37)[0]
        ahead='white' if (i<len(ah) and ah[i]=='w') else 'black'
        stm_side='white' if stm==0 else 'black'
        if wdl==0: draw+=1
        elif (wdl>0 and ahead==stm_side) or (wdl<0 and ahead!=stm_side): corr+=1   # camp designe gagne
        else: wrong+=1
    return (n,corr,draw,wrong)
f7,ah7,fb,ahb,N7,NBIG=sys.argv[1:7]; N7=int(N7); NBIG=int(NBIG)
n7,c7,d7,w7=load(f7,ah7); nb,cb,db,wb=load(fb,ahb)
fires=N7+NBIG
print("  === GATE P1-percée (precision = P(WIN-pour-le-camp-designe | fire)) ===")
if fires==0:
    print("  0 fire => P1 ne s'active pas sur ce corpus (percee imprenable rare OU predicat trop strict). "
          "INCONCLUANT — elargir gen / seeds finales de pions. (jamais 'neutre')")
    sys.exit(0)
print(f"  fires totaux={fires} (≤7p={N7}, >7p={NBIG})")
if n7:
    p7=c7/n7
    print(f"  precision ≤7p (TB EXACT) : {100*p7:.2f}%  (WIN {c7} / nulle {d7} / LOSS {w7} sur {n7})")
if nb:
    pb=cb/nb
    print(f"  precision >7p (deep-relabel d14+egdb) : {100*pb:.2f}%  (WIN {cb} / nulle {db} / LOSS {wb} sur {nb})")
# GATE = TB exact ≤7p (n>=30) ; le >7p (d14) est un support
if n7>=30:
    verdict=("ADMIS (≥99,9% = P1 est un VERDICT WIN valide => l'etage verdicts EXISTE : pile L3 = TB + arbitre-d14-au-cap + P1 + escalier + vetos)"
             if c7/n7>=0.999 else
             f"VETO ({100*c7/n7:.2f}% < 99,9% : la percee ment {d7+w7} fois => P1 rejete comme verdict ; l'etage verdicts TOMBE => pile L3 minimale TB+d14-cap+escalier+vetos)")
    print(f"  VERDICT ≤7p : {verdict}")
else:
    print(f"  ≤7p : n={n7} < 30 => puissance insuffisante pour trancher 99,9% (elargir gen / seeds finales)")
    if nb>=30: print(f"  (indicatif d14 >7p : {100*cb/nb:.2f}% sur n={nb} — proxy, pas le gate)")
PY

# --- artefacts + commit ---
cp "$W/fires7_rel.jnnw" "$ART/p1_fires7_relabeled.jnnw" 2>/dev/null || true
cp "$W/firesBig_rel.jnnw" "$ART/p1_firesBig_relabeled.jnnw" 2>/dev/null || true
commit_to_main "$ART/p1_fires7_relabeled.jnnw" "$ARTREL/p1_fires7_relabeled.jnnw" "0706 P1 fires ≤7p TB-relabeled" >/dev/null 2>&1 || true
restore_src
say ""; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0706 FIN harnais P1-percée : precision P(WIN|fire) — $([ "$N7" -ge 30 ] 2>/dev/null && echo 'gate ≤7p' || echo 'sous-puissant')" \
  && say "  ✓ RESULTS committé" || say "  ⚠ commit échoue"
say "=== 0706 FINI ==="
rm -rf "$W"
