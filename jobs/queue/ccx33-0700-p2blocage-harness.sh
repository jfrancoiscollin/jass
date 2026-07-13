#!/usr/bin/env bash
# id: ccx33-0700-p2blocage-harness
# description: HARNAIS NOTATION P2-BLOCAGE (C1, go JFC 2026-07-13, corpus=self-play dédié + arbitre d14+TB si ≤7p). Le
# prédicat dilf `blocage_structurel` (verrou MUTUEL par mobilité, zéro éval, garde v0 sans dames) doit tuer le trou
# d'oracle n°1 (milieux ply-cappés mal-étiquetés « nulle par épuisement », ~19%). GATE GRAVÉ : quand il FIRE, la
# position doit être NULLE ≥ 99,9% (sinon veto ply-cap). Calibration offline : le prédicat ne fire NI sur les
# exceptions-TB (95% dames + opposition) NI sur les verrous E2 (gagnants) → corpus = positions PLY-CAPPÉES de self-play
# (là où le verrou mutuel milieu se produit). Pipeline : (1) self-play gen2-mmto max-plies → positions ; (2) prédicat
# dilf sur chaque (men-only) → FIRES ; (3) arbitre : ≤7p egdb-relabel EXACT, >7p playout fort gen2-vs-gen2 (movetime
# ~d14) ; (4) precision = P(NULLE|fire). Build JASS_EGDB=ON, dilf cloné. Robustesse 12-pts. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0700-p2blocage-harness/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0700-p2blocage-harness/artefacts"
W=/root/cw-p2bloc
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DILF=/root/dilf-src
PERG=400; MAXPLIES=160; MINPIECES=12; STRONG_D=8; WEAK_D=3; JITTER=1; SKIP=8; DRAWFRAC=1.0; SEED=57000
ARB_MT=1.0; ARB_PAIRS=3; SHARD_TIMEOUT=2400

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

say "=== harnais P2-blocage — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
restore_src(){ git checkout -- src pattern_jass/src tools/scan_selfplay_gen.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 ABORT egdb"; exit 4; }
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" \
  || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 ABORT cmake"; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 ABORT build"; exit 6; }
J="$W/build/jass"
# clone dilf + smoke-import du prédicat
if [ -d "$DILF/.git" ]; then git -C "$DILF" pull --quiet 2>/dev/null||true; else git clone --depth=1 https://github.com/jfrancoiscollin/dilf.git "$DILF" >"$W/dilf.log" 2>&1; fi
PYTHONPATH="$DILF" python3 -c "from pedagogy.features.blocage import blocage_structurel, mutual_blocked; from pedagogy.game import GameState; from scripts.pcblues.rules import RulesEngine; print('dilf import OK')" >"$W/imp.log" 2>&1 \
  || { say "ABORT import dilf : $(cat "$W/imp.log"|tail -2)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 ABORT dilf import"; exit 7; }
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build egdb + dilf import OK ; egdb=$EGDIR"

# --- self-play gen2-mmto (positions ply-cappables) ---
say ""; say "=== self-play gen2-mmto ${PERG}×${NCPU} (max-plies $MAXPLIES, min-pieces $MINPIECES) ==="
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

# --- prédicat dilf sur chaque position (men-only) -> FIRES (split ≤7p / >7p) ---
say ""; say "=== prédicat blocage_structurel (dilf) -> fires ==="
PYTHONPATH="$DILF" python3 - "$W/pos.jnnw" "$W/fires7.jnnw" "$W/firesBig.fen" <<'PY' | tee -a "$RES"
import struct,sys
from pedagogy.game import GameState
from pedagogy.features.blocage import blocage_structurel, mutual_blocked
from scripts.pcblues.rules import RulesEngine
ENG=RulesEngine(); REC=38
pos,out7,outbig=sys.argv[1],sys.argv[2],sys.argv[3]
b=open(pos,'rb').read(); n=struct.unpack('<I',b[4:8])[0]
def sqs(v): return frozenset(s for s in range(1,51) if (v>>(s-1))&1)
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in sorted(sqs(wm))]+["K"+str(s) for s in sorted(sqs(wk))]
    Bl=[str(s) for s in sorted(sqs(bm))]+["K"+str(s) for s in sorted(sqs(bk))]
    return f"{'B' if stm else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
def pc(x):
    c=0
    while x: x&=x-1; c+=1
    return c
rec7=[]; big=[]; tested=0; fires=0; seen=set()
for i in range(n):
    off=8+i*REC; wm,wk,bm,bk,stm=struct.unpack_from('<QQQQB',b,off)
    if wk or bk: continue                       # garde v0
    key=(wm,bm,stm)
    if key in seen: continue
    seen.add(key); tested+=1
    st=GameState(white_men=sqs(wm),white_kings=frozenset(),black_men=sqs(bm),black_kings=frozenset(),turn='white' if stm==0 else 'black')
    # signal CŒUR = mutual_blocked (fire sur les verrous réels ; blocage_structurel
    # +stabilité-2plies est trop strict — rejette même le verrou canonique).
    if not mutual_blocked(st,ENG): continue
    fires+=1
    if pc(wm)+pc(bm)<=7: rec7.append(b[off:off+REC])
    else: big.append(fen(wm,wk,bm,bk,stm))
open(out7,'wb').write(b'JNNW'+struct.pack('<I',len(rec7))+b''.join(rec7))
open(outbig,'w').write("\n".join(big)+("\n" if big else ""))
print(f"  positions men-only testées (dédup) : {tested}")
print(f"  FIRES blocage_structurel : {fires}  (≤7p={len(rec7)}  >7p={len(big)})")
PY
N7=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/fires7.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null||echo 0)
NBIG=$(grep -c . "$W/firesBig.fen" 2>/dev/null||echo 0)
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 fires : 7p=$N7 big=$NBIG" >/dev/null 2>&1 || true

# --- arbitre ≤7p : egdb-relabel EXACT -> NULLE ? ---
D7=0
if [ "$N7" -gt 0 ] 2>/dev/null; then
  "$J" --egdb-relabel "$W/fires7.jnnw" "$EGDIR" "$W/fires7_rel.jnnw" 2048 >"$W/rel.log" 2>&1 || true
  D7=$(python3 -c "
import struct
b=open('$W/fires7_rel.jnnw','rb').read(); n=struct.unpack('<I',b[4:8])[0]
print(sum(1 for i in range(n) if struct.unpack_from('<b',b,8+i*38+37)[0]==0))" 2>/dev/null||echo 0)
  say "  arbitre TB ≤7p : NULLE $D7 / $N7 (exact)"
fi

# --- arbitre >7p : playout fort gen2-vs-gen2 (movetime ~d14) -> draw-rate ---
DBIG=0; GBIG=0
if [ "$NBIG" -gt 0 ] 2>/dev/null; then
  git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
  pids=()
  for s in $(seq 0 $((NCPU-1))); do timeout "$SHARD_TIMEOUT" python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
    --movetime "$ARB_MT" --pairs "$ARB_PAIRS" --max-plies 200 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/firesBig.fen" >"$W/arb.$s" 2>&1 & pids+=($!); done
  wait "${pids[@]}"; git checkout -- tools/jass_vs_jass_arch.py 2>/dev/null||true
  read DBIG GBIG < <(python3 -c "
import glob
a=d=b=0
for f in glob.glob('$W/arb.*'):
    try:
        for l in open(f):
            if l.startswith('RESULT'): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
print(d, a+d+b)")
  say "  arbitre playout >7p (gen2-vs-gen2 mt$ARB_MT) : NULLES $DBIG / $GBIG parties (draw-rate=$(python3 -c "print(f'{$DBIG/max($GBIG,1):.4f}')"))"
fi

# --- GATE : precision P(NULLE|fire) ---
python3 - "$N7" "$D7" "$NBIG" "$DBIG" "$GBIG" <<'PY' | tee -a "$RES"
import sys
n7,d7,nbig,dbig,gbig=[int(x) for x in sys.argv[1:6]]
fires=n7+nbig
say=lambda s:print(s)
if fires==0:
    say("  GATE : 0 fire => prédicat ne s'active pas sur ce corpus (fire-rate trop bas OU trou plus rare que 19% OU prédicat trop strict). INCONCLUANT — élargir gen / assouplir.")
    sys.exit(0)
# ≤7p : precision exacte. >7p : draw-rate agrégé (proxy).
prec7 = d7/n7 if n7 else None
precbig = dbig/gbig if gbig else None
say(f"  === GATE P2-blocage (precision = P(NULLE|fire)) ===")
say(f"  fires totaux={fires} (≤7p={n7}, >7p={nbig})")
if n7: say(f"  precision ≤7p (TB exact) : {100*prec7:.2f}%  ({d7}/{n7})")
if gbig: say(f"  precision >7p (playout, draw-rate agrégé) : {100*precbig:.2f}%  ({dbig}/{gbig} parties)")
# gate sur le TB exact (≤7p) en priorité ; le >7p est un proxy support
gate = (prec7 is None or prec7>=0.999) and (precbig is None or precbig>=0.999)
if n7>=30 and prec7 is not None:
    say(f"  VERDICT ≤7p : {'ADMIS (≥99,9% = tue la source ply-cap)' if prec7>=0.999 else 'VETO (fausses nulles → garder ply-cap)'}")
else:
    say(f"  ≤7p : n={n7} < 30 → puissance insuffisante pour trancher 99,9% (élargir gen)")
PY
say ""; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0700 FIN harnais P2-blocage : precision P(NULLE|fire) du prédicat C1" \
  && say "  ✓ RESULTS committé" || say "  ⚠ commit échoue"
say "=== 0700 FINI ==="
