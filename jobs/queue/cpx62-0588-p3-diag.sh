#!/usr/bin/env bash
# id: cpx62-0588-p3-diag
# description: P3 DIAGNOSTIC (JFC "derniere passe") — P3 a echoue 2x avec fits NA sans qu'on voie l'erreur. Ici on
# CAPTURE le stderr complet du fit et on le committe. Gen court (4 shards ~200k), VAL=shard0, TRAIN=shards1-3, UN fit
# 8cf@holdout + full log => on voit enfin pourquoi le fit ne sort pas HOLDOUT_LOGLOSS. Si OK, on enchaine 32cf + volumes.
# Code depuis DEVELOP (holdout-frac + 8cf). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0588-p3-diag/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0588-p3-diag/artefacts"
W=/root/cw-p3diag; rm -rf "$W"; mkdir -p "$W"; G8="$W/g8"; G32="$W/g32"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
FORCE="ext_forcing=1,forcing_ext_cap=6"; PD=6; LABEL_DEPTH=4; MAXPLIES=200; PERSHARD=200000
L2=3e-5; MAXIT=25; CHUNK=1000000
VERD="$ART/VERDICT.txt"; : > "$VERD"; say(){ echo "$@" | tee -a "$VERD"; }

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
cat_jnnw(){ python3 - "$@" <<'PY'
import struct,sys
out=sys.argv[1]; body=b""; tot=0
for f in sys.argv[2:]:
    try: b=open(f,'rb').read()
    except: continue
    if len(b)<8 or b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*38]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
}

say "=== P3 DIAG : overlay develop + build ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/gen_patterns.py > pattern_jass/tools/gen_patterns.py
say "  develop=$(git rev-parse --short origin/develop) ; train_stream a holdout-frac: $(grep -c holdout-frac pattern_jass/tools/train_stream.py)"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"; TOOLS="$(pwd)/pattern_jass/tools"
mkdir -p "$G8" "$G32"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v3 >/dev/null 2>&1 || true; cp pattern_jass/tools/patterns.py "$G8/patterns.py"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true; cp pattern_jass/tools/patterns.py "$G32/patterns.py"
N8=$(PYTHONPATH="$G8:$TOOLS" python3 -c "import patterns;print(patterns.NUM_PATTERNS)" 2>/dev/null)
say "  geom 8cf NUM_PATTERNS=$N8"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git checkout -- src/main.cpp pattern_jass/tools/gen_patterns.py 2>/dev/null || true

say "=== gen 4 shards ~$PERSHARD ==="
for s in 0 1 2 3; do "$J" --gen-data-wdl "$PERSHARD" "$W/shard.$s.jnnw" "$LABEL_DEPTH" "$PD" "$MAXPLIES" "$((RANDOM*RANDOM+s+1))" \
    --nnue "$W/gen1.pjtw" --asym-punisher-params "$FORCE" --quiet-only --explore-eps 5 --random-open-plies 8 \
    >"$W/g_$s.log" 2>&1 & done; wait
mv "$W/shard.0.jnnw" "$W/VAL.jnnw"
VALN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/VAL.jnnw','rb').read(8)[4:8])[0])" 2>&1)
cat_jnnw "$W/trainpool.jnnw" "$W"/shard.[1-3].jnnw >/dev/null
POOLN=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/trainpool.jnnw','rb').read(8)[4:8])[0])" 2>&1)
say "  VALN=$VALN  POOLN=$POOLN"

V=300000
python3 - "$W/trainpool.jnnw" "$W/VAL.jnnw" "$V" "$W/data.jnnw" <<'PY'
import struct,sys
tp=open(sys.argv[1],'rb').read(); vn=open(sys.argv[2],'rb').read(); REC=38
ntp=struct.unpack('<I',tp[4:8])[0]; V=min(int(sys.argv[3]),ntp)
recs=tp[8:8+V*REC]+vn[8:]; tot=len(recs)//REC
open(sys.argv[4],'wb').write(b'JNNW'+struct.pack('<I',tot)+recs); print("data",tot)
PY
FRAC=$(python3 -c "print($VALN/($V+$VALN))" 2>&1)
say "  V=$V  FRAC=$FRAC  data=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/data.jnnw','rb').read(8)[4:8])[0])")"

say ""; say "=== dump-features + fit 8cf (FULL LOG capturé) ==="
"$J" --dump-eval-features "$W/data.jnnw" "$W/feat" >"$W/dump.log" 2>&1; say "  dump rc=$? ($(tail -1 "$W/dump.log"))"
JASS_PATTERNS_DIR="$G8" python3 pattern_jass/tools/train_stream.py --data "$W/data.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --prune-min-visits 1 --holdout-frac "$FRAC" --out "$W/c.pjtw" >"$W/fit8.log" 2>&1
FITRC=$?
say "  fit 8cf rc=$FITRC ; HOLDOUT_LOGLOSS = $(grep -oE 'HOLDOUT_LOGLOSS [0-9.]+' "$W/fit8.log" | awk '{print $2}' || echo ABSENT)"
say ""; say "=== derniere 20 lignes du fit log (LE diagnostic) ==="
tail -20 "$W/fit8.log" | sed 's/^/  /' | tee -a "$VERD"
commit_to_main "$VERD" "$ARTREL/VERDICT.txt" "0588 P3 diag : pourquoi le fit ne sort pas HOLDOUT_LOGLOSS (log capture)" \
  && say "  VERDICT committe ✓" || say "  ⚠ commit echoue"
say "=== fin diag ==="
