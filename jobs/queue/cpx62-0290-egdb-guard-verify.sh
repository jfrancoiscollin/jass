#!/usr/bin/env bash
# id: cpx62-0290-egdb-guard-verify
# description: VERIF du guard <3-pièces. 0289 a montré 2 KvK db2 où egdb rend un décisif faux. Le fix
# (probe() décline <3 pièces + selfcheck ne flagge que le DÉCISIF) est sur main. Ici : rebuild egdb
# avec le fix + re-run --egdb-selfcheck (seed fixe, 5000 pos) → DOIT être "invariant OK, 0 violation"
# + re-confirme le self-test natif 164/164 (la base n'a pas changé). Scelle proprement la bitbase.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0290-egdb-guard-verify/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app
ls "$APP"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base absente"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo BUILD FAIL; tail -15 "$ART/build.log"; exit 5; }
./build-egdb/jass_tests 2>&1 | tail -1

echo "=== --egdb-selfcheck (5000, doit être 0 violation maintenant) ==="
./build-egdb/jass --egdb-selfcheck "$APP" 5000 2>&1 | tee "$ART/selfcheck.txt" | grep -iE 'VIOLATION|checked|egdb |KvK|RESULT'

echo "=== self-test natif (re-confirme 164/164) ==="
LIB=/root/jass/build-egdb/libegdb_intl.a
cmake --build build-egdb -j"$NCPU" --target egdb_intl >>"$ART/build.log" 2>&1
cp /root/egdb_intl/example/main.cpp /root/egex.cpp; sed -i 's#C:/db_intl/wld_v2#'"$APP"'#g' /root/egex.cpp
g++ -std=c++17 -O2 -I/root/egdb_intl /root/egex.cpp "$LIB" -lpthread -o /root/egex 2>"$ART/gpp.log" && /root/egex 2>&1 | tail -2

echo; echo "=========================================================="
echo "   cpx62-0290 — VERIF guard egdb"
echo "  'RESULT: invariant OK' + 'Test complete, 0 errors.' = bitbase scellée proprement."
echo "=========================================================="
