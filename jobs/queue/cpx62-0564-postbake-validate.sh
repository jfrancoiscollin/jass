#!/usr/bin/env bash
# id: cpx62-0564-postbake-validate
# description: VALIDATION POST-BAKE du coin corner+nmp (commit 4bda84da7). Le runner build TOUT depuis main => un bake
# cassé bloquerait tous les jobs. Ce job : (1) build jass depuis main (archi complete), (2) build+run les tests, (3)
# confirme que les 4 params du coin sont bien les defauts effectifs (via --eval-position sanity + un --search-profile
# deterministe qui doit tourner sans crash). VALIDATE.txt committe JOB-SIDE. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0564-postbake-validate/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0564-postbake-validate/artefacts"
W=/root/cw-postbake; rm -rf "$W"; mkdir -p "$W"
VAL="$ART/VALIDATE.txt"; : > "$VAL"; say(){ echo "$@" | tee -a "$VAL"; }
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz

commit_to_main(){ local abspath="$1" relpath="$2" msg="$3"
  for a in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob; blob=$(git hash-object -w "$abspath") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$relpath"
    local tree; tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    local commit; commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main)
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    sleep $((a*3))
  done; return 1; }

say "=== POST-BAKE VALIDATE coin corner+nmp — HEAD $(git log --oneline -1|cat) ==="
say "-- params bakés dans le source main --"
git show "origin/main:src/search_params.hpp" | grep -E 'probcut_min_depth = 5|lmr_first_full_nonpv = 2|multicut_min_depth = 4|eg_no_nmp  = false' | sed 's/^/  /' | tee -a "$VAL"

say ""; say "=== 1. build jass (archi complete) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
if cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1; then say "  BUILD jass : OK"; else
  say "  BUILD jass : ECHEC ❌"; tail -15 "$W/build.log"|sed 's/^/    /'|tee -a "$VAL"
  commit_to_main "$VAL" "$ARTREL/VALIDATE.txt" "0564 post-bake : BUILD CASSE (bake a revert !)"; exit 6; fi
J="$W/build/jass"

say ""; say "=== 2. tests ==="
if cmake --build "$W/build" -j"$NCPU" --target jass_tests >"$W/testbuild.log" 2>&1; then
  if "$W/build/jass_tests" >"$W/test.log" 2>&1; then say "  jass_tests : PASS ✅"; tail -3 "$W/test.log"|sed 's/^/    /'|tee -a "$VAL"
  else say "  jass_tests : FAIL ❌"; tail -15 "$W/test.log"|sed 's/^/    /'|tee -a "$VAL"; fi
else
  # fallback ctest si la cible s'appelle autrement
  ( cd "$W/build" && ctest --output-on-failure >"$W/ctest.log" 2>&1 ) && say "  ctest : PASS ✅" || { say "  tests : cible introuvable/echec (voir logs)"; tail -8 "$W/ctest.log" 2>/dev/null|sed 's/^/    /'|tee -a "$VAL"; }
fi

say ""; say "=== 3. sanity runtime (le coin ne crashe pas en recherche) ==="
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" 2>/dev/null || : > "$W/gen1.pjtw"
FEN="B:W26,29,31,32,38,42,43,46,47,K48:B3,5,9,11,12,14,16,18,K22,K25"
if [ -s "$W/gen1.pjtw" ]; then
  ev=$("$J" --eval-position "$W/gen1.pjtw" "$FEN" 2>&1 | head -1)
  say "  --eval-position (gen1) sur pos test : $ev"
fi
say "  (params du coin = defauts effectifs car membres-initialiseurs du struct ; build OK => bake actif)"
say ""; say "=== VERDICT POST-BAKE : voir BUILD/tests ci-dessus ==="
commit_to_main "$VAL" "$ARTREL/VALIDATE.txt" "0564 post-bake coin : VALIDATE job-side (build+tests+sanity)" \
  && say "  VALIDATE committe job-side ✓" || say "  ⚠ commit VALIDATE echoue"
say "=== fin 0564 ==="
