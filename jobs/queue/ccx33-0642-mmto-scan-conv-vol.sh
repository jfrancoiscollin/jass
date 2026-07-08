#!/usr/bin/env bash
# id: ccx33-0642-mmto-scan-conv-vol
# description: RONDE MMTO VOLUME — dépasser le plafond 57k (0638 seed-limité par min-pieces=40). Ici min-pieces=32 débloque
# le pool corpus-mix2M → self-play Scan asym conversion PUR (fort mt0.3 vs faible mt0.03), ancré gen2-mmto, WS ON, ~150k parents
# (cible). FIT STREAMÉ (--chunk 300000, gradient exact, plus d'OOM). Progress committé toutes les 10 min. Commit parents (pour
# la courbe de volume 0640). But : le volume au-delà de 57k fait-il progresser le fit/l'Elo ? AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0642-mmto-scan-conv-vol/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0642-mmto-scan-conv-vol/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmto-vol; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-vol
SCAN_BIN=/root/jass-scan/scan_linux
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
STRONG_MT=0.3; WEAK_MT=0.03; PERG=1200; MAXPLIES=160; MINPIECES=32; SKIP=8; DRAWFRAC=0.2
LEAFD=5; MAXPP=16; LAM=0.3; ANCHOR=0.05; WS_MARGIN=10   # WS ON

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RONDE MMTO VOLUME (ancre gen2-mmto, Scan asym conversion) — HEAD $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0638 ABORT Scan"; exit 5; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2-mmto"; exit 4; }
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; exit 4; }
say "  ✓ build+Scan+gen2-mmto ; NP=$NP ; prof Scan mt$STRONG_MT vs $WEAK_MT ; WS_margin=$WS_MARGIN (ON) ; anchor=$ANCHOR"

# ---- gen asym Scan + MONITOR progress (committé toutes les 600s : parties/parents/ETA) ----
say ""; say "=== gen Scan asym conversion (${PERG}×${NCPU} parties) — progress au fil ==="
GT0=$SECONDS; pids=()
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" --seeds "$W/seeds.jnnw" \
    --out "$W/.sp-$s.jnnw" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --strong-movetime "$STRONG_MT" --weak-movetime "$WEAK_MT" --pref-parents "$W/.pp-$s.jnnw" --pref-moves "$W/.pm-$s.bin" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" --seed 20642 --nshards "$NCPU" --shard "$s" >"$W/.sp-$s.log" 2>&1 &
  pids+=($!)
done
TOT=$((PERG*NCPU))
progress_monitor(){ while true; do sleep 600
    local alive=0 p; for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
    python3 - "$W" "$NCPU" "$TOT" "$((SECONDS-GT0))" >"$W/.prog" 2>/dev/null <<'PY' || true
import sys,glob,re
W,nc,tot,el=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]); g=0; par=0
for s in range(nc):
    try:
        last=None
        for ln in open(f"{W}/.sp-{s}.log",errors='replace'):
            m=re.search(r'(\d+)/\d+ games, (\d+) positions(?:, prefs tr=(\d+))?',ln)
            if m: last=m
        if last: g+=int(last.group(1)); par+=int(last.group(3) or 0)
    except Exception: pass
rate=g/el if el>0 else 0; eta=int((tot-g)/rate) if rate>0 else -1
print(f"  [progress] {g}/{tot} parties, {par} parents (côté fort), {el}s écoulés, ETA {eta}s (~{eta//60} min)" if eta>=0 else f"  [progress] {g}/{tot} parties, {par} parents, {el}s")
PY
    [ -s "$W/.prog" ] && { cat "$W/.prog" | tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0642 progress gen ($(cat "$W/.prog"|grep -oE '[0-9]+/[0-9]+' ))" >/dev/null 2>&1 || true; }
    [ "$alive" = 0 ] && break
  done; }
progress_monitor & MON=$!
wait "${pids[@]}"; kill "$MON" 2>/dev/null || true
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null || true

# concat parents+moves alignés
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys,os
parout,movout,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pbody=bytearray(); mbody=bytearray(); tot=0
for s in range(nc):
    pf=os.path.join(W,f".pp-{s}.jnnw"); mf=os.path.join(W,f".pm-{s}.bin")
    if not (os.path.exists(pf) and os.path.exists(mf)): continue
    pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; mb=open(mf,'rb').read()
    if len(mb)!=2*n: continue
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody)); open(movout,'wb').write(bytes(mbody))
print(f"  parents conversion = {tot}")
PY
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  parents conversion (asym Scan) : $NPAR"
[ "$NPAR" -gt 2000 ] 2>/dev/null || { say "ABORT gen vide"; exit 7; }
gzip -c "$W/parents.jnnw" > "$ART/volconv-parents.jnnw.gz"; gzip -c "$W/moves.bin" > "$ART/volconv-moves.bin.gz"
commit_to_main "$ART/volconv-parents.jnnw.gz" "$ARTREL/volconv-parents.jnnw.gz" "0642 parents conversion (min-pieces 32, gros volume) Scan asym ($NPAR)" >/dev/null 2>&1 || true
commit_to_main "$ART/volconv-moves.bin.gz" "$ARTREL/volconv-moves.bin.gz" "0642 moves conversion" >/dev/null 2>&1 || true

# ---- split + MMTO leaf-mode ancré gen2-mmto, WORKING-SET ON ----
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi: open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC]); open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
PY
say ""; say "=== MMTO gen-siblings --leaf-mode (ancre=gen2-mmto, WS ON margin=$WS_MARGIN, d$LEAFD) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WS_MARGIN" --nnue "$W/gen2.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
grep -h '^GENSIB' "$W"/gs_*.log | sed 's/^/  /' | tee -a "$RES" | tail -1
# working-set stat : combien de parents où gen2 désaccorde (émis) vs déjà d'accord (skip)
WSTOP=$(grep -hoE 'ws_already_top=[0-9]+' "$W"/gs_*.log | grep -oE '[0-9]+' | python3 -c "import sys;print(sum(int(x) for x in sys.stdin))" 2>/dev/null||echo 0)
QUSED=$(grep -hoE 'quiet_used=[0-9]+' "$W"/gs_*.log | grep -oE '[0-9]+' | python3 -c "import sys;print(sum(int(x) for x in sys.stdin))" 2>/dev/null||echo 0)
say "  working-set : $QUSED parents entraînés ; $WSTOP déjà d'accord (skippés)"
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  MMTO pairs : {tot//2}")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  MMTO paires (working-set, feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 500 ] 2>/dev/null || { say "ABORT paires (WS a tout skippé ?)"; exit 8; }

"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 9; }
say "  dump : $(tail -1 "$W/dump.log")"
say ""; say "=== rank_finetune ancré gen2-mmto --leaf-pov anchor=$ANCHOR ==="
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
    --champion "$W/gen2.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/gen3.pjtw" \
    --tools pattern_jass/tools --lam "$LAM" --anchor "$ANCHOR" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
    --full-fold --tempo-stage --leaf-pov --chunk 300000 --verify-jass "$J" --verify-n 60 >"$W/ft.log" 2>&1
if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft.log" | sed 's/^/  /' | tee -a "$RES"
  gzip -c "$W/gen3.pjtw" > "$ART/gen3vol-candidate.pjtw.gz"
  commit_to_main "$ART/gen3vol-candidate.pjtw.gz" "$ARTREL/gen3vol-candidate.pjtw.gz" "0642 candidat gen3vol (MMTO ronde 2, ancre gen2-mmto, conversion Scan, WS ON)" \
    && say "  candidat gen3 committé ✓" || say "  ⚠ commit echoue"
else say "  fit ABORT : $(tail -2 "$W/ft.log"|tr '\n' ' ')"; fi
say ""; say "  => next : A/B Elo gen3 vs gen2-mmto (cpx62) — généraliste(signal)+dilf(garde-fou) mt0.2+0.3."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0642 ronde MMTO volume (gen2-mmto->gen3, conversion Scan, WS ON) : candidat pret pour A/B" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin ronde MMTO 2 ==="
