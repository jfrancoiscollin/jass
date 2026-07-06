#!/usr/bin/env bash
# id: ccx33-0621-mmto-maitres-v2-povfix
# description: MMTO v2 — CORRIGE la contamination POV de 0620 (feuilles-PV à parités différentes → le signe par-record de
# rank_finetune était faux ; pairwise-acc pré-fit tombait à 0.307 < 0.5). Fix : gen-siblings --leaf-mode stocke le stm
# PARENT dans le champ score ; rank_finetune --leaf-pov en dérive le signe de paire (X·w est black-POV, donc la valeur des
# feuilles était correcte, seul le signe manquait). Réutilise les parents+moves maîtres committés par 0620 (pas de ré-
# extraction). DIAGNOSTIC CLÉ = pairwise-acc PRÉ-FIT : si ~0.307 → POV encore cassé ; si ≥0.5 → fix OK. Puis fit {0.1,0.3},
# candidats committés pour A/B Elo (0622, cpx62). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0621-mmto-maitres-v2-povfix/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0621-mmto-maitres-v2-povfix/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmto2; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-mmto2
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
PAR_GZ=jobs/results/ccx33-0620-mmto-maitres-v1/artefacts/maitres-parents.jnnw.gz
MOV_GZ=jobs/results/ccx33-0620-mmto-maitres-v1/artefacts/maitres-moves.bin.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
LEAFD=5; MAXPP=16; LAM=0.3; WSOFF=-1000000000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== MMTO v2 (POV fix) — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/rank_finetune.py > pattern_jass/tools/rank_finetune.py
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom $NP!=32"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
git show "origin/main:$PAR_GZ" | gunzip > "$W/parents.jnnw" || { say "ABORT parents (0620)"; exit 4; }
git show "origin/main:$MOV_GZ" | gunzip > "$W/moves.bin" || { say "ABORT moves (0620)"; exit 4; }
NPARENTS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  ✓ build develop + parents=$NPARENTS réutilisés (0620) ; NUM_PATTERNS=$NP"

# ---- split + MMTO gen (leaf-mode, stm parent en champ score) ----
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys
pf,mf,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; body=pb[8:]; mb=open(mf,'rb').read()
per=(n+nc-1)//nc
for s in range(nc):
    lo,hi=s*per,min((s+1)*per,n)
    if lo>=hi: open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',0)); open(f"{W}/ms_{s}.bin",'wb').write(b''); continue
    open(f"{W}/ps_{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',hi-lo)+body[lo*REC:hi*REC]); open(f"{W}/ms_{s}.bin",'wb').write(mb[lo*2:hi*2])
print(f"  split {nc} shards (~{per}/shard)")
PY
say ""; say "=== MMTO gen-siblings --leaf-mode (depth=$LEAFD, --nnue gen1, stm parent stocké) ==="
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
say "  MMTO paires (feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT paires"; git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null||true; exit 8; }

"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 9; }
say "  dump : $(tail -1 "$W/dump.log")"

# ---- fit --leaf-pov {0.1,0.3} : pré-fit pairwise-acc = DIAGNOSTIC POV ----
OKA=""
for A in 0.1 0.3; do
  say ""; say "=== rank_finetune MMTO --leaf-pov anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/mmto_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'leaf-pov|pairwise-acc|POV gate|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"
    gzip -c "$W/mmto_$A.pjtw" > "$ART/mmto2_$A.pjtw.gz"
    commit_to_main "$ART/mmto2_$A.pjtw.gz" "$ARTREL/mmto2_$A.pjtw.gz" "0621 candidat MMTO v2 (POV fix) anchor=$A" \
      && say "  [$A] candidat committé" || say "  [$A] ⚠ commit echoue"
  else say "  [$A] ABORT (gate) : $(tail -2 "$W/ft_$A.log"|tr '\n' ' ')"; fi
done
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py 2>/dev/null || true

say ""
say "  DIAGNOSTIC : pré-fit pairwise-acc (champion à travers la recherche vs coups maîtres) ;"
say "    0620 buggé = 0.307 (POV cassé). Ici, avec --leaf-pov : ≥0.5 attendu (fix OK) ; >0.5 = search agree masters."
say "  => next : 0622 (cpx62) A/B Elo mmto2_{0.1,0.3} vs gen1 (harnais 0619)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0621 MMTO v2 POV fix : candidats corrigés + diagnostic pré-fit pairwise-acc" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin MMTO v2 ==="
