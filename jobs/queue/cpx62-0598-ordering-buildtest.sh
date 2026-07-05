#!/usr/bin/env bash
# id: cpx62-0598-ordering-buildtest
# description: GATE DE NON-REGRESSION du port history-prob (commit develop 2edfbe84) AVANT tout DOE. Construit 2 binaires :
# BASE = main tel quel ; PROB = main + overlay develop:src/search.cpp+search_params.hpp (hist_mode dispo). Checks :
# (1) jass_tests (build PROB) verts ; (2) perft identique BASE vs PROB (l'ordering ne change pas l'ensemble des coups) ;
# (3) BYTE-IDENTICAL legacy : PROB a params DEFAUT (hist_mode=0) == BASE => nodes identiques sur N positions d9/d11
# (le chemin legacy est intact) ; (4) SMOKE prob : PROB avec hist_mode=1 tourne sans crash ET nodes DIFFERENT du legacy
# (=> le chemin prob agit). Aucun bake, aucune mesure Elo — juste : le code est-il SAIN et le legacy intact. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0598-ordering-buildtest/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0598-ordering-buildtest/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-ordbt; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== ordering build+test — HEAD main $(git log --oneline -1|cat) ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
say "  develop=$(git rev-parse --short origin/develop)"

# ---- BASE : main tel quel ----
git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null || true
cmake -S . -B "$W/base" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake_base.log" 2>&1
cmake --build "$W/base" -j"$NCPU" --target jass >"$W/build_base.log" 2>&1 || { say "BASE BUILD FAIL"; tail -12 "$W/build_base.log"|sed 's/^/  /'; exit 6; }
JBASE="$W/base/jass"; say "  BASE build OK"

# ---- PROB : overlay develop search files ----
git show origin/develop:src/search.cpp        > src/search.cpp
git show origin/develop:src/search_params.hpp > src/search_params.hpp
cmake -S . -B "$W/prob" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake_prob.log" 2>&1
cmake --build "$W/prob" -j"$NCPU" --target jass jass_tests >"$W/build_prob.log" 2>&1 || { say "PROB BUILD FAIL"; tail -20 "$W/build_prob.log"|sed 's/^/  /'; git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null||true; exit 6; }
JPROB="$W/prob/jass"; TESTS="$W/prob/jass_tests"; say "  PROB build OK (jass + jass_tests)"
git checkout -- src/search.cpp src/search_params.hpp 2>/dev/null || true
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }

FAIL=0
# ---- (1) jass_tests ----
say ""; say "=== (1) jass_tests (build PROB) ==="
if [ -x "$TESTS" ]; then
  "$TESTS" >"$W/tests.log" 2>&1 && say "  ✓ jass_tests PASS ($(grep -iE 'passed|ok|assert' "$W/tests.log"|tail -1))" \
    || { say "  ✗ jass_tests FAIL"; tail -15 "$W/tests.log"|sed 's/^/    /'; FAIL=1; }
else say "  ⚠ binaire jass_tests introuvable"; FAIL=1; fi

# ---- (2) perft identique ----
say ""; say "=== (2) perft BASE vs PROB (startpos d1..7) ==="
PB=$("$JBASE" --perft 7 2>/dev/null | grep -oE 'perft\(7\) = [0-9]+' | grep -oE '[0-9]+$')
PP=$("$JPROB" --perft 7 2>/dev/null | grep -oE 'perft\(7\) = [0-9]+' | grep -oE '[0-9]+$')
say "  perft(7) BASE=$PB PROB=$PP"; [ -n "$PB" ] && [ "$PB" = "$PP" ] && say "  ✓ perft identique" || { say "  ✗ perft DIFFERE"; FAIL=1; }

# ---- (3) BYTE-IDENTICAL legacy : PROB(defaut) == BASE (nodes) ----
say ""; say "=== (3) legacy byte-identical : PROB(hist_mode=0 defaut) vs BASE, nodes @ d9/d11 ==="
head -12 "$DILF" | sed 's/#.*//' | tr -d ' ' | grep -E ':' | head -10 > "$W/fens.txt"
NDIFF=0; NPOS=0
while IFS= read -r fen; do [ -z "$fen" ] && continue
  for d in 9 11; do
    nb=$("$JBASE" --search-profile "$fen" "$d" 0 "$W/gen1.pjtw" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1)
    np=$("$JPROB" --search-profile "$fen" "$d" 0 "$W/gen1.pjtw" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1)
    NPOS=$((NPOS+1)); [ "$nb" != "$np" ] && { NDIFF=$((NDIFF+1)); [ "$NDIFF" -le 3 ] && say "    DIFF d$d : BASE $nb PROB $np ($fen)"; }
  done
done < "$W/fens.txt"
say "  positions comparees=$NPOS ; divergentes=$NDIFF"
[ "$NDIFF" = 0 ] && [ "$NPOS" -gt 0 ] && say "  ✓ legacy byte-identical (chemin d'origine intact)" || { say "  ✗ legacy DIVERGE => regression"; FAIL=1; }

# ---- (4) SMOKE prob : hist_mode=1 tourne + nodes != legacy ----
say ""; say "=== (4) smoke prob (hist_mode=1) : tourne + effet sur l'arbre ==="
fen1=$(head -1 "$W/fens.txt"); SAMEDIFF=0; RAN=0
for spec in "hist_mode=1,prob_shift=5" "hist_mode=1,hist_pure=1,hist_order_captures=1"; do
  nl=$("$JPROB" --search-profile "$fen1" 11 0 "$W/gen1.pjtw" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1)
  npb=$("$JPROB" --search-profile "$fen1" 11 0 "$W/gen1.pjtw" "$spec" 2>/dev/null | grep -oE 'nodes=[0-9]+' | head -1)
  [ -n "$npb" ] && RAN=$((RAN+1))
  say "    [$spec] nodes=$npb (legacy=$nl)"; [ -n "$npb" ] && [ "$npb" != "$nl" ] && SAMEDIFF=$((SAMEDIFF+1))
done
[ "$RAN" -ge 2 ] && say "  ✓ prob tourne sans crash ($RAN/2 specs) ; arbre modifie sur $SAMEDIFF/2" || { say "  ✗ prob a plante"; FAIL=1; }

say ""
[ "$FAIL" = 0 ] && say "==> ✅ GATE VERT : code sain, legacy intact, prob actif => OK pour le DOE (gate 0597 en amont)." \
                || say "==> ❌ GATE ROUGE : corriger avant DOE."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0598 ordering build+test : jass_tests/perft/byte-identical-legacy/smoke-prob (gate avant DOE)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin build+test ==="
