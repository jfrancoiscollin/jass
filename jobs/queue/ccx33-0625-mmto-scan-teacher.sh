#!/usr/bin/env bash
# id: ccx33-0625-mmto-scan-teacher
# description: MMTO v4 QUALITÉ — remplace le prof 2000-Elo (mode PLAYED bruité, coup humain faillible) par le COUP CHOISI
# PAR SCAN (surhumain, fiable) sur les mêmes parents maîtres. Attaque le handicap #1 (fiabilité du prof) : le champion-à-
# travers-recherche est déjà d'accord avec les 2000-maîtres à 0.686, et une part des 31% de désaccord = le maître qui se
# trompe. Scan comme prof supprime ce bruit d'étiquette. Pipeline : parents maîtres (0624) -> Scan score chaque parent
# (go, mt) -> coup Scan = prof -> gen-siblings --leaf-mode --leaf-pov (feuilles-PV, POV fixé) -> fit -> candidats pour A/B.
# book=false (ScanEngine). Coups Scan-capture/échec -> (0,0) -> gen-siblings no_match-skip (alignement préservé). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0625-mmto-scan-teacher/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0625-mmto-scan-teacher/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmtoscan; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-mmtoscan
SCAN_BIN=/root/jass-scan/scan_linux
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
PAR_GZ=jobs/results/ccx33-0624-mmto-maitres-v3-highvol/artefacts/maitres-parents.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
SCAN_MT=0.2; LEAFD=5; MAXPP=16; LAM=0.3; WSOFF=-1000000000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== MMTO v4 teacher-Scan — HEAD main $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan indisponible"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0625 ABORT Scan absent"; exit 5; }

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
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$PAR_GZ" | gunzip > "$W/parents.jnnw" || { say "ABORT parents (0624)"; exit 4; }
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  ✓ build + Scan + parents=$NPAR ; NUM_PATTERNS=$NP ; Scan-teacher mt=$SCAN_MT"

# ---- driver Scan : coup Scan = prof, par parent (aligné, (0,0) si capture/échec) ----
cat > "$W/scandrv.py" <<'PY'
import sys,struct
sys.path.insert(0,'tools')
import calibrate_vs_scan as cv
from scan_selfplay_gen import record_to_fen
par,scan_bin,jass_bin,shard,ns,out,mt=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5]),sys.argv[6],float(sys.argv[7])
d=open(par,'rb').read(); n=struct.unpack('<I',d[4:8])[0]; body=d[8:]; REC=38
per=(n+ns-1)//ns; lo=shard*per; hi=min((shard+1)*per,n)
scan=cv.ScanEngine(scan_bin); ref=cv.Referee(jass_bin)
mv=bytearray(); ncap=0; nfail=0; nquiet=0
for i in range(lo,hi):
    rec=body[i*REC:(i+1)*REC]
    try:
        fen,pc=record_to_fen(rec)
        ref.set_position_fen(fen); sp,sm=ref.scan_pos()
        m=scan.go_from(sp,sm,movetime=mt)
        if m is None: mv+=bytes([0,0]); nfail+=1
        elif m.is_capture: mv+=bytes([0,0]); ncap+=1
        elif 1<=m.frm<=50 and 1<=m.to<=50: mv+=bytes([m.frm,m.to]); nquiet+=1
        else: mv+=bytes([0,0]); nfail+=1
    except Exception: mv+=bytes([0,0]); nfail+=1
open(out,'wb').write(bytes(mv))
try: scan.close(); ref.close()
except Exception: pass
sys.stderr.write(f"shard {shard}: quiet={nquiet} cap={ncap} fail={nfail}\n")
PY
say ""; say "=== Scan score les parents (coup Scan = prof, ×$NCPU shards) ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 "$W/scandrv.py" "$W/parents.jnnw" "$SCAN_BIN" "$J" "$s" "$NCPU" "$W/mv_$s.bin" "$SCAN_MT" 2>"$W/drv_$s.log" &
done; wait
grep -h '^shard' "$W"/drv_*.log | sed 's/^/  /' | tee -a "$RES"
# concat en ORDRE (slices contiguës) -> aligné parents
python3 - "$W/moves.bin" "$W" "$NCPU" <<'PY'
import sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); b=bytearray()
for s in range(nc):
    f=f"{W}/mv_{s}.bin"
    if os.path.exists(f): b+=open(f,'rb').read()
open(out,'wb').write(bytes(b)); print(f"  scan-moves : {len(b)//2} (aligné parents)")
PY
NQUIET=$(python3 -c "b=open('$W/moves.bin','rb').read();print(sum(1 for i in range(0,len(b),2) if b[i]!=0))")
say "  coups Scan quiets exploitables : $NQUIET / $NPAR"
gzip -c "$W/moves.bin" > "$ART/scan-teacher-moves.bin.gz"
commit_to_main "$ART/scan-teacher-moves.bin.gz" "$ARTREL/scan-teacher-moves.bin.gz" "0625 scan-teacher moves (aligné parents 0624)" >/dev/null 2>&1 || true

# ---- split + MMTO gen leaf-mode (prof=coup Scan) ----
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi: open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC]); open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
print(f"  split {nc} shards")
PY
say ""; say "=== MMTO gen-siblings --leaf-mode (prof=Scan, --nnue gen1, depth=$LEAFD) ==="
for s in $(seq 0 $((NCPU-1))); do
  "$J" --gen-siblings "$W/ps_$s.jnnw" "$W/pairs_$s.jnnw" "$LEAFD" --played-moves "$W/ms_$s.bin" \
       --leaf-mode --ws-margin "$WSOFF" --nnue "$W/gen1.pjtw" --max-pairs-per-parent "$MAXPP" >"$W/gs_$s.log" 2>&1 &
done; wait
grep -h '^GENSIB' "$W"/gs_*.log | sed 's/^/  /' | tee -a "$RES" | tail -1
python3 - "$W/pairs.jnnw" "$W" "$NCPU" <<'PY'
import struct,sys,os
out,W,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38; body=bytearray(); tot=0
for s in range(nc):
    f=f"{W}/pairs_{s}.jnnw"
    if not os.path.exists(f): continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(f"  MMTO pairs : {tot//2} paires")
PY
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)")
say "  MMTO paires (prof Scan, feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT paires"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null||true; exit 8; }

"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 9; }
say "  dump : $(tail -1 "$W/dump.log")"
OKA=""
for A in 0.05 0.1; do
  say ""; say "=== rank_finetune MMTO teacher-Scan --leaf-pov anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/scanmmto_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"
    gzip -c "$W/scanmmto_$A.pjtw" > "$ART/scanmmto_$A.pjtw.gz"
    commit_to_main "$ART/scanmmto_$A.pjtw.gz" "$ARTREL/scanmmto_$A.pjtw.gz" "0625 candidat MMTO teacher-Scan anchor=$A" \
      && say "  [$A] candidat committé" || say "  [$A] ⚠ commit echoue"
  else say "  [$A] ABORT (gate) : $(tail -2 "$W/ft_$A.log"|tr '\n' ' ')"; fi
done
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null || true

say ""
say "  DIAGNOSTIC : pré-fit pairwise-acc = accord champion-à-travers-recherche vs COUP SCAN (prof surhumain fiable)."
say "  vs 0621 (prof 2000 = 0.686). Si le prof Scan donne un fit plus fort / un delta plus net => la qualité du prof était le frein."
say "  => next : A/B Elo scanmmto_{0.05,0.1} vs gen1 (cpx62, harnais 0619)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0625 MMTO teacher-Scan : candidats prets pour A/B (test qualite du prof)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin MMTO teacher-Scan ==="
