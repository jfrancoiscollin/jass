#!/usr/bin/env bash
# id: cpx62-0289-egdb-fens
# description: DIAG rapide. 0288 : self-test natif egdb 164/164 (autoritaire = OK) MAIS notre
# --egdb-selfcheck a flaggé 2 "KvK-no-capture NOT draw" (invariant). Le tail -3 a mangé les FEN.
# Ici on RE-RUN le selfcheck (seed fixe = reproductible) avec sortie COMPLÈTE pour capturer les 2
# positions, + on dump leurs coups légaux (y a-t-il VRAIMENT 0 capture ?) et la valeur egdb. Tranche :
# détecteur-de-capture buggé (faux positif) vs vraie fissure de conversion sur 2 positions.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0289-egdb-fens/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x build-egdb/jass ] || { cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
  cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }; }

echo "=== selfcheck COMPLET (2000, seed fixe) — capture des violations ==="
./build-egdb/jass --egdb-selfcheck "$APP" 2000 2>&1 | tee "$ART/full.txt" | grep -iE 'VIOLATION|egdb self-check|checked|egdb |KvK|RESULT'
echo
echo "=== les FEN flaggées ==="
grep -iE 'VIOLATION' "$ART/full.txt" | sed -n '1,12p'

echo; echo "=========================================================="
echo "   cpx62-0289 — FEN des 2 violations KvK (diag conversion vs détecteur)"
echo "=========================================================="
