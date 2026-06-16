#!/usr/bin/env bash
# id: ccx33-0302-mtc-probe
# description: VALIDE la lecture MTC (sonde codée dans egdb_bridge) + révèle la distribution des
# distances-à-la-conversion — pour designer la cible-gradient (a). Build JASS_EGDB (vérifie aussi que
# is_mtc/egdb_lookup MTC compilent contre egdb_intl), puis `--egdb-mtc-probe WLD MTC 30000` : pour des
# positions aléatoires quiètes, WLD-probe ; sur un gain/perte, MTC-probe → distribution (1=<10 plies,
# sinon le compte). 0 valeurs "bad" + signal présent = MTC lisible → on peut coder la labellisation.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0302-mtc-probe/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTC=/root/egdb_mtc/app
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: base WLD absente"; exit 4; }
ls "$MTC"/*.idx_mtc >/dev/null 2>&1 || { echo "ABORT: base MTC absente ($MTC)"; exit 4; }
echo "MTC files: $(ls "$MTC"/*.idx_mtc 2>/dev/null | wc -l)"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1

rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -25 "$ART/build.log"; exit 5; }
./build-egdb/jass_tests 2>&1 | tail -1

echo "=== --egdb-mtc-probe (30000 positions) ==="
./build-egdb/jass --egdb-mtc-probe "$WLD" "$MTC" 30000 1024 2>&1 | tail -25

echo; echo "=========================================================="
echo "   ccx33-0302 — VALIDATION sonde MTC"
echo "  'MTC readable, conversion-distance signal present' → on code la labellisation-gradient :"
echo "  outil offline : position ≤8 → (WLD win/loss) ? distance MTC → cible graduée → train l'éval."
echo "=========================================================="
