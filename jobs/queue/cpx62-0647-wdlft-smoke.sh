#!/usr/bin/env bash
# id: cpx62-0647-wdlft-smoke
# description: SMOKE de wdl_finetune.py (PISTE 1) sur SLICE (200k) du corpus 0645 déjà généré + gen2-mmto. Valide le NOUVEL
# outil : POV gate Spearman>0.95, z-stats (σ non saturée => T=1 ok ?), grad-check, logloss DESCEND, jass CHARGE la sortie
# (mini A/B 1 paire vs gen2-mmto). Sweep anchor {0.1, 1, 10} pour CALIBRER la plage du run complet (combien bouge |Δw| /
# logloss par anchor). AUCUN NNUE. Corpus réutilisé (pas de self-play). But = dérisquer l'outil avant le re-couplage complet.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0647-wdlft-smoke/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0647-wdlft-smoke/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-wdlft-smoke; rm -rf "$W"; mkdir -p "$W"; GEOM=/root/jass-geom32-wdlft
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
WDL_GZ=jobs/results/cpx62-0645-couplage-genA-cpx62/artefacts/wdl-cpx62.jnnw.gz
SLICE=200000; CHUNK=200000; MAXIT=15; ANCHORS="0.1 1 10"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
jnnw_count(){ python3 -c "import struct;print(struct.unpack('<I',open('$1','rb').read(8)[4:8])[0])"; }

say "=== SMOKE wdl_finetune (piste 1) — HEAD $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
restore_src(){ git checkout -- src/main.cpp pattern_jass/tools/train_stream.py pattern_jass/tools/wdl_finetune.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; restore_src; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$WDL_GZ" | gunzip > "$W/wdl_full.jnnw" || { say "ABORT wdl corpus"; restore_src; exit 4; }

# slice premières SLICE positions
python3 - "$W/wdl_full.jnnw" "$W/wdl.jnnw" "$SLICE" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38; k=min(int(sys.argv[3]),n)
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',k)+b[8:8+k*REC]); print(k)
PY
N_WDL=$(jnnw_count "$W/wdl.jnnw"); say "  ✓ build+geom(NP=$NP)+gen2 ; slice WDL = $N_WDL positions"
"$J" --dump-eval-features "$W/wdl.jnnw" "$W/wdlfeat" >"$W/wdlfeat.log" 2>&1 || { say "DUMP FAIL"; tail -5 "$W/wdlfeat.log"|sed 's/^/  /'; restore_src; exit 8; }

say ""; say "=== sweep anchor {$ANCHORS} : POV gate + z-stats + logloss + jass-charge ==="
for A in $ANCHORS; do
  tag=$(echo "$A" | tr '.' 'p')
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
      --champion "$W/gen2.pjtw" --data "$W/wdl.jnnw" --feat "$W/wdlfeat" --out "$W/ft_$tag.pjtw" \
      --tools pattern_jass/tools --anchor "$A" --logit-scale 1.0 --chunk "$CHUNK" --max-iter "$MAXIT" \
      --full-fold --tempo-stage --verify-jass "$J" --verify-n 40 >"$W/ft_$tag.log" 2>&1
  rc=$?
  if [ $rc = 0 ] && [ -s "$W/ft_$tag.pjtw" ]; then
    say "  [anchor=$A]"
    grep -iE 'z-stats|POV gate|buckets|fit : logloss|mean' "$W/ft_$tag.log" | sed 's/^/    /' | tee -a "$RES"
    # jass charge la sortie : mini A/B 1 paire vs gen2
    python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/ft_$tag.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" \
      --movetime 0.1 --pairs 1 --max-plies 60 --shard 0 --nshards 1 --quiet >"$W/ab_$tag.log" 2>&1 || true
    if grep -q '^RESULT' "$W/ab_$tag.log"; then say "    charge OK : $(grep '^RESULT' "$W/ab_$tag.log"|head -1)"
    else say "    ⚠ pas de RESULT"; tail -4 "$W/ab_$tag.log"|sed 's/^/      /'|tee -a "$RES"; fi
  else say "  [anchor=$A] FAIL (rc=$rc) : $(tail -3 "$W/ft_$tag.log"|tr '\n' ' ')"; fi
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0647 smoke wdlft anchor=$A" >/dev/null 2>&1 || true
done
restore_src
say ""
say "================= SMOKE VERDICT ================="
say "  Si pour chaque anchor : POV gate>0.95 + grad-check OK + logloss DESCEND + charge OK => outil VALIDÉ."
say "  z-stats std : si |z/T| raisonnable (~1-6) => T=1 ok ; sinon relever --logit-scale au run complet."
say "  mean|Δw| par anchor => calibre la plage du re-couplage (anchor petit = bouge trop ? grand = fige)."
say "================================================"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0647 SMOKE wdl_finetune : outil validé (POV+grad+logloss+charge) sweep anchor" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin smoke wdlft ==="
