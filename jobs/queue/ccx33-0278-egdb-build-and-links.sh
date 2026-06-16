#!/usr/bin/env bash
# id: ccx33-0278-egdb-build-and-links
# description: SUITE de 0277. Acquis : la boxe ATTEINT edgilbert.org (200 OK) → pas besoin de toucher
# la policy réseau. 0277 a planté le build pour une raison TRIVIALE : /tmp inutilisable sur la boxe,
# j'avais oublié export TMPDIR=/root/jass/.compile-tmp (que tous les autres jobs mettent). Ici :
# (1) TMPDIR fix → build JASS_EGDB=ON from-source + 6428 tests + perft (valide la chaîne sur la boxe).
# (2) dump la page de download edgilbert + le listing du répertoire parent vers stdout (les fichiers
# artefacts restent server-side, donc je dois CAT le HTML pour récupérer les URLs exactes des bases).
# Ensuite je code 0279 = download d'une tranche ≤6 pièces + --egdb-selfcheck (doit être CLEAN).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0278-egdb-build-and-links/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc)
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"   # <-- le fix (0277 l'avait oublié)

echo "=== (1) build JASS_EGDB=ON from-source (TMPDIR fixé) ==="
rm -rf /root/egdb_intl
git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1 \
  && echo "clone egdb_intl OK" || { echo "CLONE FAIL"; tail -5 "$ART/clone.log"; }
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" && echo "cmake: EGDB ENABLED"
cmake --build build-egdb -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 \
  && echo "BUILD OK" || { echo "BUILD FAIL"; tail -30 "$ART/build.log"; }
[ -x build-egdb/jass ]       && ./build-egdb/jass --perft 6 2>/dev/null | tail -1
[ -x build-egdb/jass_tests ] && ./build-egdb/jass_tests 2>&1 | tail -1
[ -x build-egdb/jass ]       && ./build-egdb/jass --egdb-selfcheck /root/egdb_intl 50 2>&1 | head -2

echo; echo "=== (2) page de download + listing répertoire (pour les URLs de base) ==="
BASE="http://edgilbert.org/InternationalDraughts"
PAGE="$BASE/endgame_database_downloads.htm"
echo "----- FULL PAGE HTML ($PAGE) -----"
curl -s --max-time 40 "$PAGE" 2>/dev/null | tee "$ART/page.html"
echo; echo "----- tous les href de la page -----"
grep -oiE 'href="[^"]+"' "$ART/page.html" 2>/dev/null | sort -u
echo "----- listing du répertoire parent (autoindex ?) -----"
curl -s --max-time 40 "$BASE/" 2>/dev/null | grep -oiE 'href="[^"]+"' | sort -u | head -60
echo "----- sous-dossiers probables (db/, wld/, intl/) -----"
for sub in db wld wld_v2 intldb databases endgame; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$BASE/$sub/" 2>/dev/null)
  echo "  $BASE/$sub/ -> HTTP $code"
done

echo; echo "=========================================================="
echo "   ccx33-0278 — EGDB BUILD (boxe) + LIENS DE BASE"
echo "----------------------------------------------------------"
echo "  build : voir 'BUILD OK' + 6428 tests + perft(6)=167140"
echo "  liens : voir 'FULL PAGE HTML' + href ci-dessus → je code 0279 (download tranche ≤6p + selfcheck)"
echo "=========================================================="
