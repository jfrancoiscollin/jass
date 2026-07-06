#!/usr/bin/env bash
# id: ccx33-0627-mmto-scan-selfplay-highvol
# description: MMTO v5 — PLUS DE VOLUME + MEILLEURE QUALITÉ + MEILLEUR PROF, tout Scan (demande JFC). Les positions ne
# viennent plus du DB maîtres (plafonné 44k, humaines 2000) mais de SELF-PLAY SCAN asymétrique (fort mt0.3 vs faible
# mt0.03, book=false 2 côtés) : volume illimité + on-distribution pour un prof Scan. Le PROF = le coup joué par le côté
# FORT (= choix de Scan, surhumain) — extrait directement (pas de re-scoring). Puis MMTO --leaf-mode --leaf-pov (feuilles-PV,
# POV fixé) sur ~72k parents. Isole si le trio {volume + positions Scan + prof Scan} débloque ce que les maîtres (0621/0624
# plats +0.002) et le Scan-teacher-sur-positions-maîtres (0625) ne débloquent pas. Candidats committés pour A/B. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0627-mmto-scan-selfplay-highvol/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0627-mmto-scan-selfplay-highvol/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mmtosp; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-mmtosp
SCAN_BIN=/root/jass-scan/scan_linux
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
STRONG_MT=0.3; WEAK_MT=0.03; PERG=1300; MAXPLIES=160; MINPIECES=40; SKIP=8; DRAWFRAC=0.2
LEAFD=5; MAXPP=16; LAM=0.3; WSOFF=-1000000000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== MMTO v5 Scan self-play haut-volume — HEAD main $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan indisponible"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0627 ABORT Scan absent"; exit 5; }

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
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; exit 4; }
say "  ✓ build + Scan + seeds ; NUM_PATTERNS=$NP ; prof Scan mt=$STRONG_MT (vs faible $WEAK_MT)"

# ---- Scan self-play asym : parents = positions Scan (côté fort), coup fort = prof Scan ----
say ""; say "=== Scan self-play asym (book=false, fort mt$STRONG_MT vs faible mt$WEAK_MT, ${PERG}×${NCPU} parties) ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" \
    --seeds "$W/seeds.jnnw" --out "$W/.sp-$s.jnnw" --games "$PERG" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --strong-movetime "$STRONG_MT" --weak-movetime "$WEAK_MT" \
    --pref-parents "$W/.pp-$s.jnnw" --pref-moves "$W/.pm-$s.bin" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" \
    --seed 20627 --nshards "$NCPU" --shard "$s" >"$W/.sp-$s.log" 2>&1 &
done; wait
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null || true
grep -h '^wrote .*strong-side' "$W"/.sp-*.log | sed 's/^/  /' | tee -a "$RES" | tail -2
# concat parents+moves alignés (ordre shards)
python3 - "$W/parents.jnnw" "$W/moves.bin" "$W" "$NCPU" <<'PY'
import struct,sys,os
parout,movout,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]); REC=38
pbody=bytearray(); mbody=bytearray(); tot=0
for s in range(nc):
    pf=os.path.join(W,f".pp-{s}.jnnw"); mf=os.path.join(W,f".pm-{s}.bin")
    if not (os.path.exists(pf) and os.path.exists(mf)): continue
    pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]; mb=open(mf,'rb').read()
    if len(mb)!=2*n: print(f"  [WARN] shard {s} misalign {len(mb)}!=2*{n}"); continue
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody)); open(movout,'wb').write(bytes(mbody))
print(f"  parents Scan = {tot} (prof = coup Scan côté fort)")
PY
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])")
say "  parents Scan self-play : $NPAR"
[ "$NPAR" -gt 2000 ] 2>/dev/null || { say "ABORT gen vide"; exit 7; }
gzip -c "$W/parents.jnnw" > "$ART/scan-sp-parents.jnnw.gz"; gzip -c "$W/moves.bin" > "$ART/scan-sp-moves.bin.gz"
commit_to_main "$ART/scan-sp-parents.jnnw.gz" "$ARTREL/scan-sp-parents.jnnw.gz" "0627 parents Scan self-play ($NPAR, réutilisable)" >/dev/null 2>&1 || true
commit_to_main "$ART/scan-sp-moves.bin.gz" "$ARTREL/scan-sp-moves.bin.gz" "0627 moves Scan self-play (prof fort)" >/dev/null 2>&1 || true

# ---- split + MMTO gen leaf-mode (prof = coup Scan côté fort) ----
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
say ""; say "=== MMTO gen-siblings --leaf-mode (prof=Scan fort, --nnue gen1, depth=$LEAFD) ==="
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
say "  MMTO paires (positions+prof Scan, feuilles-PV) : $NPAIRS"
[ "$NPAIRS" -gt 1000 ] 2>/dev/null || { say "ABORT paires"; exit 8; }

"$J" --dump-eval-features "$W/pairs.jnnw" "$W/feat" >"$W/dump.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/dump.log"|sed 's/^/  /'; exit 9; }
say "  dump : $(tail -1 "$W/dump.log")"
OKA=""
for A in 0.05 0.1; do
  say ""; say "=== rank_finetune MMTO Scan-selfplay --leaf-pov anchor=$A ==="
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/rank_finetune.py \
      --champion "$W/gen1.pjtw" --pairs "$W/pairs.jnnw" --feat "$W/feat" --out "$W/spmmto_$A.pjtw" \
      --tools pattern_jass/tools --lam "$LAM" --anchor "$A" --min-pairs 5 --rank-scale 1.0 --max-iter 60 \
      --full-fold --tempo-stage --leaf-pov --verify-jass "$J" --verify-n 60 >"$W/ft_$A.log" 2>&1
  if [ $? = 0 ]; then grep -E 'pairwise-acc|delta' "$W/ft_$A.log" | sed "s/^/  [$A] /" | tee -a "$RES"; OKA="$OKA $A"
    gzip -c "$W/spmmto_$A.pjtw" > "$ART/spmmto_$A.pjtw.gz"
    commit_to_main "$ART/spmmto_$A.pjtw.gz" "$ARTREL/spmmto_$A.pjtw.gz" "0627 candidat MMTO Scan-selfplay anchor=$A ($NPAR parents)" \
      && say "  [$A] candidat committé" || say "  [$A] ⚠ commit echoue"
  else say "  [$A] ABORT (gate) : $(tail -2 "$W/ft_$A.log"|tr '\n' ' ')"; fi
done
git checkout -- src/main.cpp pattern_jass/tools/rank_finetune.py tools/scan_selfplay_gen.py 2>/dev/null || true

say ""
say "  DIAGNOSTIC : pré-fit pairwise-acc + delta. Positions Scan + prof Scan + volume $NPAR (vs 44k maîtres)."
say "  Si delta net (>> +0.002 des maîtres) => le trio volume+distribution+prof Scan débloque la marge => scale + A/B + boucle externe."
say "  Si toujours ~0 => l'éval linéaire à-travers-recherche est MAXÉE (le search capte déjà tout), marge close définitivement."
say "  => next : A/B Elo spmmto_{0.05,0.1} vs gen1 (cpx62)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0627 MMTO Scan self-play haut-volume : candidats prets pour A/B" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin MMTO Scan self-play ==="
