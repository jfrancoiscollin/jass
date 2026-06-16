#!/usr/bin/env bash
# id: ccx33-0277-egdb-probe
# description: PROBE bitbase (préparer le job download+selfcheck). Le download des bases tourne
# SUR LA BOXE (pas dans le container Claude, bloqué par le proxy Anthropic edgilbert.org=403).
# (1) reachability edgilbert.org depuis la boxe + dump des liens/tailles de base. (2) valide le
# build JASS_EGDB=ON FROM-SOURCE sur la boxe (clone egdb_intl) + 6428 tests + perft + selfcheck
# sans-data (doit échouer proprement, pas crasher). Léger (~min). Décide la suite : boxe atteint
# edgilbert.org → on enchaîne le job download (≤4-6 pièces) + --egdb-selfcheck (doit être CLEAN) ;
# sinon → blocage côté boxe à débloquer.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0277-egdb-probe/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc)

echo "=== (1) reachability edgilbert.org depuis la boxe ==="
URL="http://edgilbert.org/InternationalDraughts/endgame_database_downloads.htm"
curl -sI --max-time 25 "$URL" > "$ART/head.txt" 2>&1; RC=$?
sed -n '1,8p' "$ART/head.txt"
echo "curl head rc=$RC  (0 + '200/30x' = boxe ATTEINT edgilbert.org)"

echo "=== (2) dump des liens de base (href + tailles) ==="
curl -s --max-time 40 "$URL" > "$ART/page.html" 2>/dev/null || true
echo "page bytes: $(wc -c < "$ART/page.html" 2>/dev/null || echo 0)"
grep -oiE 'href="[^"]+"' "$ART/page.html" 2>/dev/null | sort -u > "$ART/links.txt" || true
echo "--- liens DB potentiels (db|wld|piece|.zip|.7z|.cpr) ---"
grep -oiE 'href="[^"]*(db|wld|piece|\.zip|\.7z|\.cpr|\.idx)[^"]*"' "$ART/page.html" 2>/dev/null | sort -u | head -40
echo "--- tout texte mentionnant tailles GB/MB + nombre de pièces ---"
grep -oiE '[0-9]+ ?(piece|GB|MB)' "$ART/page.html" 2>/dev/null | sort -u | head -30

echo "=== (3) build JASS_EGDB=ON from-source sur la boxe + tests ==="
rm -rf /root/egdb_intl
git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1 \
  && echo "clone egdb_intl OK" || { echo "CLONE FAIL"; tail -5 "$ART/clone.log"; }
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" && echo "cmake: EGDB ENABLED" || { echo "cmake KO"; tail -10 "$ART/cmake.log"; }
cmake --build build-egdb -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 \
  && echo "BUILD OK" || { echo "BUILD FAIL"; tail -25 "$ART/build.log"; }
[ -x build-egdb/jass ]       && ./build-egdb/jass --perft 6 2>/dev/null | tail -1
[ -x build-egdb/jass_tests ] && ./build-egdb/jass_tests 2>&1 | tail -1
# selfcheck sans data : doit reporter l'échec d'init proprement (pas de crash).
[ -x build-egdb/jass ]       && ./build-egdb/jass --egdb-selfcheck /root/egdb_intl 100 2>&1 | head -2

echo; echo "=========================================================="
echo "   ccx33-0277 — PROBE BITBASE"
echo "----------------------------------------------------------"
echo "  reachability rc=$RC  (voir head.txt ; 200/30x = OK)"
echo "  liens DB     : $ART/links.txt  (+ filtrés ci-dessus)"
echo "  build EGDB   : voir BUILD OK + 6428 tests + perft(6)=167140"
echo "----------------------------------------------------------"
echo "  SUITE si reachable : job download (db ≤4-6 pièces) → --egdb-selfcheck (DOIT être CLEAN)"
echo "  SUITE si bloqué    : débloquer le réseau côté boxe (firewall sortant)"
echo "=========================================================="
