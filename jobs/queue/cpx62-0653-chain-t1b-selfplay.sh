#!/usr/bin/env bash
# id: cpx62-0653-chain-t1b-selfplay
# description: CHAÎNE ITÉRATIVE LONGUE (mémo JFC) — TOUR 1, SELF-PLAY. Pilote = champion(0)=gen2-mmto qui DRIVE la
# distribution (mobile, cœur du mémo : PAS Scan-as-player=statique). jass self-asym par DEPTH (fort d12 vs faible d6 = teacher FORT + positions DISPUTÉES,
# randomisé/partie) => WDL (outcomes) + prefs MMTO côté-FORT (recherche d12 >> feuille d5 = vrai teacher ; d6 pas écrasé = prefs de qualité). asym pur
# (pas de flotte balanced — leçon starvation-mix). min-pieces 32. Nouvel outil `scan_selfplay_gen --player-jass` (validé
# py_compile). TAILLE MODESTE (~0.5M) + monitor ETA committé /10min : premier ancrage TIMING jass-self-play réel — je
# RESIZE le tour suivant dessus (règle timing). Corpus committé (WDL + prefs) pour le fit tour-1 (wdl_finetune ancré
# gen2-mmto anchor 0.3 + MMTO last). AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0653-chain-t1b-selfplay/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0653-chain-t1b-selfplay/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-chain-t1b; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
# TOUR 1 : modeste (ancrage timing). strong d8 vs weak d3, jitter 1.
PERG=200; MAXPLIES=160; MINPIECES=32; SKIP=8; DRAWFRAC=0.2
STRONG_D=12; WEAK_D=6; JITTER=1; SEED=50653

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
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== CHAÎNE tour 1 SELF-PLAY (pilote=gen2-mmto, self-asym d$STRONG_D/d$WEAK_D) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
restore_src(){ git checkout -- src/main.cpp tools/scan_selfplay_gen.py tools/calibrate_vs_scan.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
JB=$(( NCPU>4 ? NCPU : 4 )); cmake --build "$W/build" -j"$JB" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -15 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0650 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+gen2 ; seeds=$(jnnw_count "$W/seeds.jnnw") ; PERG=$PERG×$NCPU strong d$STRONG_D vs weak d$WEAK_D (jitter $JITTER)"

# ---- self-play champion asym (WDL + prefs) ----
say ""; say "=== gen champion self-asym : ${PERG}×${NCPU} parties ==="
GT0=$SECONDS; pids=()
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/gen2.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$s" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" \
    --sample-every 1 --depth "$STRONG_D" --weak-depth "$WEAK_D" --depth-jitter "$JITTER" \
    --pref-parents "$W/pp.$s" --pref-moves "$W/pm.$s.bin" --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed "$SEED" --nshards "$NCPU" --shard "$s" >"$W/sp-$s.log" 2>&1 &
  pids+=($!)
done
TOT=$((PERG*NCPU))
( while true; do sleep 600
    alive=0; for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
    python3 - "$W" "$NCPU" "$TOT" "$((SECONDS-GT0))" >"$W/.prog" 2>/dev/null <<'PY' || true
import sys,glob,re
W,nc,tot,el=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]); g=0;pos=0;par=0
for s in range(nc):
    try:
        last=None
        for ln in open(f"{W}/sp-{s}.log",errors='replace'):
            m=re.search(r'(\d+)/\d+ games, (\d+) positions(?:, prefs tr=(\d+))?',ln)
            if m: last=m
        if last: g+=int(last.group(1));pos+=int(last.group(2));par+=int(last.group(3) or 0)
    except Exception: pass
rate=g/el if el>0 else 0; eta=int((tot-g)/rate) if rate>0 else -1
print(f"  [progress] {g}/{tot} parties, {pos} positions, {par} prefs, {el}s"+(f", ETA ~{eta//60} min ({pos*tot//max(g,1)} pos proj.)" if eta>=0 else ""))
PY
    [ -s "$W/.prog" ] && { cat "$W/.prog"|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0653 progress ($(cat "$W/.prog"|grep -oE '[0-9]+/[0-9]+'|head -1))" >/dev/null 2>&1||true; }
    [ "$alive" = 0 ] && break
  done ) & MON=$!
wait "${pids[@]}"; kill "$MON" 2>/dev/null||true
restore_src

N_WDL=$(merge_jnnw "$W/wdl.jnnw" "$W/sp"); say "  WDL positions = $N_WDL ($((SECONDS-GT0))s, $(( TOT*3600/(SECONDS-GT0+1) )) parties/h)"
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys,os
parout,movout,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pbody=bytearray(); mbody=bytearray(); tot=0
for s in range(nc):
    pf=os.path.join(W,f"pp.{s}"); mf=os.path.join(W,f"pm.{s}.bin")
    if not (os.path.exists(pf) and os.path.exists(mf)): continue
    pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; mb=open(mf,'rb').read()
    if len(mb)!=2*n: continue
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody)); open(movout,'wb').write(bytes(mbody))
print(tot)
PY
N_PAR=$(jnnw_count "$W/parents.jnnw"); say "  prefs côté-fort = $N_PAR parents"
[ "$N_WDL" -gt 20000 ] 2>/dev/null || { say "⚠ WDL faible ($N_WDL) — le player jass a-t-il tourné ? voir sp-0.log"; tail -8 "$W/sp-0.log"|sed 's/^/    /'|tee -a "$RES"; }

gzip -c "$W/wdl.jnnw" > "$ART/chain-t1b-wdl.jnnw.gz"
gzip -c "$W/parents.jnnw" > "$ART/chain-t1b-prefs-parents.jnnw.gz"
gzip -c "$W/moves.bin" > "$ART/chain-t1b-prefs-moves.bin.gz"
commit_to_main "$ART/chain-t1b-wdl.jnnw.gz" "$ARTREL/chain-t1b-wdl.jnnw.gz" "0653 tour1b WDL ($N_WDL)" >/dev/null 2>&1||true
commit_to_main "$ART/chain-t1b-prefs-parents.jnnw.gz" "$ARTREL/chain-t1b-prefs-parents.jnnw.gz" "0653 tour1b prefs ($N_PAR)" >/dev/null 2>&1||true
commit_to_main "$ART/chain-t1b-prefs-moves.bin.gz" "$ARTREL/chain-t1b-prefs-moves.bin.gz" "0653 tour1b moves" >/dev/null 2>&1||true
say ""; say "  => tour 1 self-play FINI : WDL=$N_WDL prefs=$N_PAR. Timing réel ci-dessus = ancre pour resize. Next : fit wdl_finetune ancré gen2 anchor 0.3 + MMTO last + gate Elo."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0653 tour1b self-play FINI : WDL=$N_WDL prefs=$N_PAR (ancrage timing jass-self-play)" && say "  RESULTS committé ✓" || say "  ⚠ commit"
say "=== fin tour1 self-play ==="
