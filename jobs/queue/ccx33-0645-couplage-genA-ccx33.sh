#!/usr/bin/env bash
# id: ccx33-0645-couplage-genA-ccx33
# description: COUPLAGE Phase-A — GENERATION part ccx33 (⅓ du volume). Une passe self-play Scan = 2 objectifs (WDL + prefs
# MMTO). 2 flottes : BAL équilibré fort-vs-fort d8/d9/d10 (prefs OFF, WDL calibré) + ASYM mt0.3/mt0.03 (WDL décisif + prefs
# côté-fort). Sharding GLOBAL disjoint (nshards=48, ccx33 BAL=32..39 ASYM=40..47 ; cpx62 job = 0..31) => aucune ouverture
# dupliquée entre flottes NI entre box. Commit corpus WDL gz + prefs gz + PROGRESS committé toutes les 10 min (parties/
# positions/ETA). Le fit WDL->MMTO + A/B = job séparé (après que les 2 gen aient committé). Ancrage smoke 0644 : ~128 pos/
# partie, ~27 prefs/partie ASYM. AUCUN NNUE. Corpus régénérable (seuls corpus/prefs committés comme artefacts).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0645-couplage-genA-ccx33/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-cplA-ccx33; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-cplA
SCAN_BIN=/root/jass-scan/scan_linux
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# --- Phase-A sizing (ccx33 = ⅓) : 8 shards/flotte × 490 = 3920 BAL + 3920 ASYM = 7840 parties ≈ 1.0M positions ---
NSH=8; GLOBAL_NSHARDS=48; BAL_BASE=32; ASYM_BASE=40; SEED=50645
PERG=490; MAXPLIES=160; MINPIECES=32; SKIP=8; DRAWFRAC=0.2
BAL_DEPTH=10; BAL_JITTER=2; STRONG_MT=0.3; WEAK_MT=0.03

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

# progress monitor : parse bal-*.log + asym-*.log, commit toutes les 600s (parties/positions/prefs/ETA)
mon_pids=(); GT0=0
start_monitor(){ GT0=$SECONDS; mon_pids=("$@"); local tot="$MON_TOT" label="$MON_LABEL"
  ( while true; do sleep 600
      local alive=0 p; for p in "${mon_pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
      python3 - "$W" "$((SECONDS-GT0))" "$tot" "$label" >"$W/.prog" 2>/dev/null <<'PY' || true
import sys,glob,re
W,el,tot,label=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]; g=0; pos=0; par=0
for f in glob.glob(f"{W}/{label}-*.log"):
    try:
        last=None
        for ln in open(f,errors='replace'):
            m=re.search(r'(\d+)/\d+ games, (\d+) positions(?:, prefs tr=(\d+))?',ln)
            if m: last=m
        if last: g+=int(last.group(1)); pos+=int(last.group(2)); par+=int(last.group(3) or 0)
    except Exception: pass
rate=g/el if el>0 else 0; eta=int((tot-g)/rate) if rate>0 else -1
msg=f"  [progress {label}] {g}/{tot} parties, {pos} positions"+(f", {par} prefs" if par else "")+f", {el}s"
print(msg+(f", ETA ~{eta//60} min" if eta>=0 else ""))
PY
      [ -s "$W/.prog" ] && { cat "$W/.prog" | tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0645 progress $label ($(cat "$W/.prog"|grep -oE '[0-9]+/[0-9]+'|head -1))" >/dev/null 2>&1 || true; }
      [ "$alive" = 0 ] && break
    done ) & MON=$!; }
stop_monitor(){ kill "$MON" 2>/dev/null || true; }

say "=== COUPLAGE Phase-A GEN ccx33 (⅓) — HEAD $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0645 ABORT Scan"; exit 5; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
restore_src(){ git checkout -- src/main.cpp tools/scan_selfplay_gen.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+Scan+geom (NP=$NP) ; seeds=$(jnnw_count "$W/seeds.jnnw") ; NSH=$NSH PERG=$PERG (BAL base=$BAL_BASE, ASYM base=$ASYM_BASE, /$GLOBAL_NSHARDS)"

# ---- flotte BAL (équilibré d8/d9/d10, prefs OFF) ----
say ""; say "=== BAL équilibré d${BAL_DEPTH} jitter${BAL_JITTER} (prefs OFF) : ${PERG}×${NSH} ==="
BT0=$SECONDS; pids=()
for s in $(seq 0 $((NSH-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" --seeds "$W/seeds.jnnw" \
    --out "$W/bal.$s" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --depth "$BAL_DEPTH" --depth-jitter "$BAL_JITTER" --seed "$SEED" --nshards "$GLOBAL_NSHARDS" --shard $((BAL_BASE+s)) >"$W/bal-$s.log" 2>&1 &
  pids+=($!)
done
MON_TOT=$((PERG*NSH)); MON_LABEL=bal; start_monitor "${pids[@]}"
wait "${pids[@]}"; stop_monitor
N_BAL=$(merge_jnnw "$W/wdl_bal.jnnw" "$W/bal"); say "  WDL BAL positions = $N_BAL ($((SECONDS-BT0))s, $(( (PERG*NSH)*3600/(SECONDS-BT0+1) )) parties/h)"

# ---- flotte ASYM (mt0.3/0.03, WDL + prefs côté-fort) ----
say ""; say "=== ASYM mt${STRONG_MT}/${WEAK_MT} (WDL + prefs) : ${PERG}×${NSH} ==="
AT0=$SECONDS; pids=()
for s in $(seq 0 $((NSH-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" --seeds "$W/seeds.jnnw" \
    --out "$W/asym.$s" --games "$PERG" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --strong-movetime "$STRONG_MT" --weak-movetime "$WEAK_MT" \
    --pref-parents "$W/pp.$s" --pref-moves "$W/pm.$s.bin" --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed "$SEED" --nshards "$GLOBAL_NSHARDS" --shard $((ASYM_BASE+s)) >"$W/asym-$s.log" 2>&1 &
  pids+=($!)
done
MON_TOT=$((PERG*NSH)); MON_LABEL=asym; start_monitor "${pids[@]}"
wait "${pids[@]}"; stop_monitor
N_ASYM=$(merge_jnnw "$W/wdl_asym.jnnw" "$W/asym"); say "  WDL ASYM positions = $N_ASYM ($((SECONDS-AT0))s)"
restore_src

# ---- merge WDL box-corpus + concat prefs ----
python3 - "$W/wdl.jnnw" "$W/wdl_bal.jnnw" "$W/wdl_asym.jnnw" <<'PY'
import struct,sys
outp=sys.argv[1]; REC=38; body=bytearray(); tot=0
for f in sys.argv[2:]:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  WDL corpus ccx33 (BAL+ASYM) = $N_WDL positions"
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NSH" <<'PY'
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
N_PAR=$(jnnw_count "$W/parents.jnnw"); say "  prefs ASYM parents ccx33 = $N_PAR"
[ "$N_WDL" -gt 100000 ] 2>/dev/null || { say "⚠ WDL corpus faible ($N_WDL)"; }

gzip -c "$W/wdl.jnnw"     > "$ART/wdl-ccx33.jnnw.gz"
gzip -c "$W/parents.jnnw" > "$ART/prefs-parents-ccx33.jnnw.gz"
gzip -c "$W/moves.bin"    > "$ART/prefs-moves-ccx33.bin.gz"
commit_to_main "$ART/wdl-ccx33.jnnw.gz" "$ARTREL/wdl-ccx33.jnnw.gz" "0645 WDL corpus ccx33 ($N_WDL)" >/dev/null 2>&1 || true
commit_to_main "$ART/prefs-parents-ccx33.jnnw.gz" "$ARTREL/prefs-parents-ccx33.jnnw.gz" "0645 prefs parents cpx62 ($N_PAR)" >/dev/null 2>&1 || true
commit_to_main "$ART/prefs-moves-ccx33.bin.gz" "$ARTREL/prefs-moves-ccx33.bin.gz" "0645 prefs moves cpx62" >/dev/null 2>&1 || true

say ""; say "  => ccx33 gen fait : WDL=$N_WDL prefs=$N_PAR committés. Attend cpx62 (0645-cpx62) puis fit/A-B."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0645 gen ccx33 FINI : WDL=$N_WDL prefs=$N_PAR" && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin gen ccx33 ==="
