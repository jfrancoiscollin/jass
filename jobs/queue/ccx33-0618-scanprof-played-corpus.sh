#!/usr/bin/env bash
# id: ccx33-0618-scanprof-played-corpus
# description: SCAN-PROF PHASE 0 (mode PLAYED). Génère un corpus de PRÉFÉRENCES depuis Scan self-play ASYMÉTRIQUE :
# Scan-FORT (mt 0.3s) vs Scan-FAIBLE (mt 0.03s), book=false DES DEUX CÔTÉS (obligatoire — le livre récite + score=0).
# Le fort convertit => parties décisives. On extrait UNIQUEMENT les coups du côté FORT (le faible est bruit volontaire),
# quiets, hors-book (skip 8 plies), filtre décisif (toutes parties décisives + 20% de nulles-tenues), holdout PAR PARTIE
# (hash ouverture, 1/10). Sortie = paires (coup joué ≻ sœurs) via gen-siblings --played-moves (pipeline bras M validé).
# Nourrit PHASE 1 bootstrap statique (rank_finetune, juge Elo 0617) — indépendant du verdict 0617 (scale-up OU sauvetage).
# AUCUN NNUE. Scan = amorce de préférence, pas destination (décision JFC). CHILD-SCORED (marges) = follow-up.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0618-scanprof-played-corpus/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0618-scanprof-played-corpus/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-scanprof; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# --- params phase 0 PLAYED ---
STRONG_MT=0.3; WEAK_MT=0.03; PERG=1000; MAXPLIES=160; MINPIECES=40
SKIP=8; DRAWFRAC=0.2; HOMOD=10; MAXPP=16

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== SCAN-PROF PHASE 0 PLAYED — HEAD main $(git log --oneline -1|cat) ==="

# ---- Scan (amorce) : présent (persisté) ou clone ; ABORT propre si absent ----
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT : Scan indisponible ($SCAN_BIN) — clone ne fournit pas le binaire. Build Scan requis (follow-up)."; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0618 ABORT Scan absent"; exit 5; }
say "  ✓ Scan : $SCAN_BIN"

# ---- jass depuis develop (gen-siblings + referee scan-parity) ----
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:tools/scan_selfplay_gen.py > tools/scan_selfplay_gen.py
git show origin/develop:src/main.cpp > src/main.cpp
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; git checkout -- src/main.cpp tools/scan_selfplay_gen.py 2>/dev/null||true; exit 6; }
J="$W/build/jass"
say "  ✓ jass (develop) build OK"

# ---- seeds : pool d'ouvertures >=${MINPIECES}p ----
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || { say "ABORT seeds"; git checkout -- src/main.cpp tools/scan_selfplay_gen.py 2>/dev/null||true; exit 4; }
say "  seeds : $(python3 -c "import struct;print(struct.unpack('<I',open('$W/seeds.jnnw','rb').read(8)[4:8])[0])") positions"

# ---- génération Scan self-play asym (book=false) + extraction préférences côté FORT ----
say ""; say "=== gen Scan asym (strong mt=$STRONG_MT vs weak mt=$WEAK_MT, book=false 2 côtés, ${PERG}×${NCPU} parties) ==="
for s in $(seq 0 $((NCPU-1))); do
  python3 tools/scan_selfplay_gen.py --scan "$SCAN_BIN" --jass "$J" \
    --seeds "$W/seeds.jnnw" --out "$W/.sp-$s.jnnw" --games "$PERG" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPIECES" --sample-every 1 \
    --strong-movetime "$STRONG_MT" --weak-movetime "$WEAK_MT" \
    --pref-parents "$W/.pp-$s.jnnw" --pref-moves "$W/.pm-$s.bin" \
    --holdout-parents "$W/.hp-$s.jnnw" --holdout-moves "$W/.hm-$s.bin" \
    --skip-book "$SKIP" --keep-draw-frac "$DRAWFRAC" --holdout-mod "$HOMOD" \
    --seed 20618 --nshards "$NCPU" --shard "$s" >"$W/.sp-$s.log" 2>&1 &
done
wait
git checkout -- src/main.cpp tools/scan_selfplay_gen.py 2>/dev/null || true
grep -h '^wrote .*parents' "$W"/.sp-*.log | sed 's/^/  /' | tee -a "$RES" | tail -3
# distributions agrégées (decisive / draws-kept)
sumtok(){ grep -ho "$1=[0-9]*" "$W"/.sp-*.log | grep -o '[0-9]*' | python3 -c "import sys;print(sum(int(x) for x in sys.stdin))" 2>/dev/null || echo 0; }
DEC=$(sumtok decisive-games); DRW=$(sumtok draws-kept)
say "  agrégé : parties décisives=$DEC ; nulles-tenues=$DRW"

# ---- concaténation shards (train + holdout), alignement parent[i] <-> move[i] préservé ----
concat(){ local tag="$1" parout="$2" movout="$3"; python3 - "$tag" "$parout" "$movout" "$W" "$NCPU" <<'PY'
import struct,sys,os
tag,parout,movout,W,nc=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]); REC=38
pbody=bytearray(); mbody=bytearray(); tot=0
for s in range(nc):
    pf=os.path.join(W,f".{'pp' if tag=='train' else 'hp'}-{s}.jnnw")
    mf=os.path.join(W,f".{'pm' if tag=='train' else 'hm'}-{s}.bin")
    if not (os.path.exists(pf) and os.path.exists(mf)): continue
    pb=open(pf,'rb').read(); n=struct.unpack('<I',pb[4:8])[0]
    mb=open(mf,'rb').read()
    if len(mb)!=2*n:  # alignment guard
        print(f"  [WARN] shard {s} {tag}: moves {len(mb)}!=2*{n}"); continue
    pbody+=pb[8:8+n*REC]; mbody+=mb; tot+=n
open(parout,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(pbody))
open(movout,'wb').write(bytes(mbody))
print(f"  {tag} : {tot} parents ({len(mbody)//2} moves)")
PY
}
say ""; say "=== concat ==="
concat train "$W/parents.jnnw" "$W/moves.bin" | tee -a "$RES"
concat holdout "$W/ho_parents.jnnw" "$W/ho_moves.bin" | tee -a "$RES"
NPAR=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/parents.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "$NPAR" -gt 1000 ] 2>/dev/null || { say "  ABORT : extraction quasi-vide (parents=$NPAR)"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0618 extraction vide"; exit 7; }

# ---- gen-siblings --played-moves : (coup fort ≻ sœurs légales), src=MASTER, sans recherche ----
say ""; say "=== gen-siblings --played-moves (train + holdout) ==="
"$J" --gen-siblings "$W/parents.jnnw" "$W/pairs.jnnw" 0 --played-moves "$W/moves.bin" --max-pairs-per-parent "$MAXPP" >"$W/gs_tr.log" 2>&1 || { say "GENSIB train FAIL"; tail -5 "$W/gs_tr.log"|sed 's/^/  /'; exit 8; }
grep -h '^GENSIB' "$W/gs_tr.log" | sed 's/^/  train /' | tee -a "$RES"
NHO=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/ho_parents.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
if [ "$NHO" -gt 200 ] 2>/dev/null; then
  "$J" --gen-siblings "$W/ho_parents.jnnw" "$W/ho_pairs.jnnw" 0 --played-moves "$W/ho_moves.bin" --max-pairs-per-parent "$MAXPP" >"$W/gs_ho.log" 2>&1 || say "  GENSIB holdout FAIL (non bloquant)"
  grep -h '^GENSIB' "$W/gs_ho.log" | sed 's/^/  holdout /' | tee -a "$RES"
fi
NPAIRS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pairs.jnnw','rb').read(8)[4:8])[0]//2)" 2>/dev/null || echo 0)
NHOP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/ho_pairs.jnnw','rb').read(8)[4:8])[0]//2)" 2>/dev/null || echo 0)
say "  paires : train=$NPAIRS ; holdout=$NHOP"

# ---- manifest (flag on => effet mesuré ; leçon +18 phantom) ----
say ""; say "=== MANIFEST ==="
say "  book=false (2 côtés)   : appliqué par ScanEngine (set-param book=false au handshake)"
say "  asym-movetime          : fort=$STRONG_MT s / faible=$WEAK_MT s (ratio $(python3 -c "print(round($STRONG_MT/$WEAK_MT,1))")×)"
say "  extraction côté FORT   : garantie code (skip si side!=strong_color) ; quiet-only ('x' exclu) ; skip-book=$SKIP"
say "  filtre décisif         : décisives=$DEC + nulles-tenues=$DRW (frac=$DRAWFRAC)"
say "  holdout PAR PARTIE     : md5(ouverture)%$HOMOD==0 -> train=$NPAR / holdout=$NHO parents (disjoints par ouverture)"
say "  volumes                : $NPAR parents -> $NPAIRS paires (train) ; $NHO -> $NHOP (holdout)"

# ---- commit corpus (train + holdout) + RESULTS ----
gzip -c "$W/pairs.jnnw" > "$ART/scanprof-played-pairs.jnnw.gz"
commit_to_main "$ART/scanprof-played-pairs.jnnw.gz" "$ARTREL/scanprof-played-pairs.jnnw.gz" "0618 corpus Scan-prof PLAYED train ($NPAIRS paires, fort mt$STRONG_MT vs faible mt$WEAK_MT)" \
  && say "  corpus train committe ($(du -h "$ART/scanprof-played-pairs.jnnw.gz"|cut -f1))" || say "  ⚠ commit train echoue"
if [ "$NHOP" -gt 100 ] 2>/dev/null; then
  gzip -c "$W/ho_pairs.jnnw" > "$ART/scanprof-played-holdout.jnnw.gz"
  commit_to_main "$ART/scanprof-played-holdout.jnnw.gz" "$ARTREL/scanprof-played-holdout.jnnw.gz" "0618 corpus Scan-prof PLAYED holdout ($NHOP paires, par partie)" \
    && say "  holdout committe" || say "  ⚠ commit holdout echoue"
fi
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0618 Scan-prof phase 0 PLAYED : corpus préférences prêt pour phase 1 (bootstrap statique, juge Elo)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit RESULTS echoue"
say "  => next PHASE 1 : rank_finetune sur ce corpus {anchor 0.01,0.1} + A/B Elo vs gen1 (harnais 0617)."
say "=== fin phase 0 PLAYED ==="
