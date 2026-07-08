#!/usr/bin/env bash
# id: cpx62-0644-couplage-smoke
# description: SMOKE end-to-end du COUPLAGE WDL<->MMTO (avant le gros run Phase-A). Valide TOUS les joints à TOUTE PETITE
# échelle (~128 parties BAL + ~128 ASYM, fit tiny) : (1) flotte BAL = Scan équilibré fort-vs-fort d8/d9/d10 (jitter), prefs
# OFF, WDL only ; (2) flotte ASYM = mt0.3 vs mt0.03, WDL + prefs côté-fort ; (3) MERGE cross-flotte des corpus WDL ; (4) fit
# WDL frais (train_stream --target wdl --color-fold --tempo-stage --l2 3e-5, gradient exact streamé) sur corpus Scan-outcome ;
# (5) MMTO gen-siblings --leaf-mode WS-OFF ancré sur la WDL-base fraîche + rank_finetune --leaf-pov anchor=0 ; (6) round-trip :
# jass charge wdlbase ET gen3 + mini A/B 1-paire. BUT = attraper toute erreur de format/reporting AVANT le run 12-16h. AUCUN
# NNUE. Corpus jetable. Reporting RESULTS committé write->read vérifié.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0644-couplage-smoke/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0644-couplage-smoke/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-couplage-smoke; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-cpl-smoke
SCAN_BIN=/root/jass-scan/scan_linux
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# --- SMOKE sizing : tiny ---
PERG_BAL=8; PERG_ASYM=8; MAXPLIES=160; MINPIECES=32; SKIP=8; DRAWFRAC=0.2
BAL_DEPTH=10; BAL_JITTER=2                       # d8/d9/d10
STRONG_MT=0.3; WEAK_MT=0.03
LEAFD=5; MAXPP=16; LAM=0.3; ANCHOR=0; WS_OFF=-1000000000   # WS-OFF obligatoire (0641 : WS-ON=-354 Elo)
L2=3e-5; MAXIT_WDL=6; CHUNK=200000; MAXIT_RANK=20

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

# merge JNNW shards written as PREFIX.0 PREFIX.1 ... into one JNNW file
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

say "=== SMOKE COUPLAGE WDL<->MMTO — HEAD $(git log --oneline -1|cat) ==="
# ---- Scan + build jass(develop) + geom ----
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0644 ABORT Scan"; exit 5; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py pattern_jass/tools/train_stream.py tools/scan_selfplay_gen.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; restore_src; exit 4; }
say "  ✓ build+Scan+geom (NP=$NP) ; seeds=$(jnnw_count "$W/seeds.jnnw")"

# ---- (1) flotte BAL : Scan équilibré d8/d9/d10, prefs OFF, WDL only ----
say ""; say "=== (1) gen BAL équilibré d${BAL_DEPTH} jitter${BAL_JITTER} (prefs OFF) : ${PERG_BAL}×${NCPU} ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" --seeds "$W/seeds.jnnw" \
    --out "$W/bal.$s" --games "$PERG_BAL" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --depth "$BAL_DEPTH" --depth-jitter "$BAL_JITTER" --seed 30644 --nshards $((NCPU*4)) --shard "$s" >"$W/bal-$s.log" 2>&1 &
done; wait
N_BAL=$(merge_jnnw "$W/wdl_bal.jnnw" "$W/bal"); say "  WDL BAL positions = $N_BAL"

# ---- (2) flotte ASYM : mt0.3 vs mt0.03, WDL + prefs côté-fort ----
say ""; say "=== (2) gen ASYM mt${STRONG_MT}/${WEAK_MT} (WDL + prefs) : ${PERG_ASYM}×${NCPU} ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" --seeds "$W/seeds.jnnw" \
    --out "$W/asym.$s" --games "$PERG_ASYM" --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --strong-movetime "$STRONG_MT" --weak-movetime "$WEAK_MT" \
    --pref-parents "$W/pp.$s" --pref-moves "$W/pm.$s.bin" --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed 40644 --nshards $((NCPU*4)) --shard $((NCPU+s)) >"$W/asym-$s.log" 2>&1 &
done; wait
N_ASYM=$(merge_jnnw "$W/wdl_asym.jnnw" "$W/asym"); say "  WDL ASYM positions = $N_ASYM"

# ---- (3) MERGE cross-flotte des corpus WDL ----
python3 - "$W/wdl.jnnw" "$W/wdl_bal.jnnw" "$W/wdl_asym.jnnw" <<'PY'
import struct,sys
outp=sys.argv[1]; REC=38; body=bytearray(); tot=0
for f in sys.argv[2:]:
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  (3) WDL corpus mergé (BAL+ASYM) = $N_WDL positions"
[ "$N_WDL" -gt 200 ] 2>/dev/null || { say "ABORT WDL corpus vide"; restore_src; exit 7; }

# ---- prefs ASYM : concat parents+moves alignés ----
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
N_PAR=$(jnnw_count "$W/parents.jnnw"); say "  prefs ASYM parents (côté fort) = $N_PAR"
[ "$N_PAR" -gt 50 ] 2>/dev/null || { say "ABORT prefs vides"; restore_src; exit 7; }

# ---- (4) fit WDL frais (streamé exact) sur corpus Scan-outcome ----
say ""; say "=== (4) fit WDL frais : train_stream --target wdl --color-fold --tempo-stage --l2 $L2 (chunk $CHUNK) ==="
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/wdlfeat.log" 2>&1 || { say "DUMP wdlfeat FAIL"; tail -5 "$W/wdlfeat.log"|sed 's/^/  /'; restore_src; exit 8; }
env JASS_PATTERNS_DIR="$GEOM" python3 pattern_jass/tools/train_stream.py --data "$W/wdl.jnnw" --feat "$W/wdlfeat" \
    --target wdl --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT_WDL" --chunk "$CHUNK" \
    --out "$W/wdlbase.pjtw" >"$W/wdlfit.log" 2>&1 || { say "TRAIN WDL FAIL"; tail -12 "$W/wdlfit.log"|sed 's/^/  /'; restore_src; exit 9; }
grep -iE 'target=wdl|train.?loss|iter|wrote' "$W/wdlfit.log" | tail -3 | sed 's/^/  /' | tee -a "$RES"
[ -s "$W/wdlbase.pjtw" ] || { say "ABORT wdlbase absent"; restore_src; exit 9; }
say "  wdlbase.pjtw = $(stat -c%s "$W/wdlbase.pjtw" 2>/dev/null||echo 0) bytes"

# ---- (5) MMTO ancré WDL-base fraîche : gen-siblings --leaf-mode WS-OFF + rank_finetune --leaf-pov anchor=0 ----
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
say ""; say "=== (5) MMTO gen-siblings --leaf-mode WS-OFF (ancre=wdlbase, d$LEAFD) + rank_finetune anchor=$ANCHOR ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WS_OFF" --nnue "$W/wdlbase.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
N_PAIRS=$(( $(jnnw_count "$W/pairs.jnnw") / 2 )); say "  MMTO paires (feuilles-PV, WS-OFF) = $N_PAIRS"
[ "$N_PAIRS" -gt 20 ] 2>/dev/null || { say "ABORT paires"; restore_src; exit 10; }
"$J" --dump-eval-features "$W/pairs.jnnw" "$W/pairfeat" >"$W/pairfeat.log" 2>&1 || { say "DUMP pairfeat FAIL"; restore_src; exit 10; }
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
    --champion "$W/wdlbase.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/pairfeat" --out "$W/gen3.pjtw" \
    --tools pattern_jass/tools --lam "$LAM" --anchor "$ANCHOR" --min-pairs 5 --rank-scale 1.0 --max-iter "$MAXIT_RANK" \
    --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 20 >"$W/rank.log" 2>&1 || { say "RANK FAIL"; tail -12 "$W/rank.log"|sed 's/^/  /'; restore_src; exit 11; }
grep -E 'pairwise-acc|delta' "$W/rank.log" | sed 's/^/  /' | tee -a "$RES"
[ -s "$W/gen3.pjtw" ] || { say "ABORT gen3 absent"; restore_src; exit 11; }

# ---- (6) round-trip : jass charge wdlbase ET gen3 + mini A/B 1-paire ----
say ""; say "=== (6) round-trip : jass charge wdlbase + gen3 (mini A/B 1 paire) ==="
python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/gen3.pjtw" --jass-b "$J" --pattern-b "$W/wdlbase.pjtw" \
  --movetime 0.1 --pairs 1 --max-plies 60 --shard 0 --nshards 1 --quiet >"$W/ab.log" 2>&1 || true
if grep -q '^RESULT' "$W/ab.log"; then say "  A/B charge OK : $(grep '^RESULT' "$W/ab.log"|head -1)"
else say "  ⚠ A/B pas de RESULT — voir ab.log"; tail -5 "$W/ab.log"|sed 's/^/    /'|tee -a "$RES"; fi

restore_src
say ""
say "================= SMOKE VERDICT ================="
say "  WDL corpus=$N_WDL (BAL $N_BAL + ASYM $N_ASYM) | prefs parents=$N_PAR | MMTO paires=$N_PAIRS"
say "  Tous les joints traversés (gen BAL+ASYM -> merge -> fit WDL -> MMTO -> charge). Prêt pour Phase-A si counts>0 & pas de FAIL."
say "================================================"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0644 smoke couplage WDL<->MMTO : joints validés (WDL=$N_WDL, prefs=$N_PAR, paires=$N_PAIRS)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin smoke couplage ==="
