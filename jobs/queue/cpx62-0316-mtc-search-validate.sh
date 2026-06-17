#!/usr/bin/env bash
# id: cpx62-0316-mtc-search-validate
# description: Valide MTC-in-search (jeu TB distance-aware). Joue des finales gagnantes ≤7p avec le search
# COMPLET, MTC chargé vs ply-seul, et compare WON% / STALL(50-coups)% / plies-moyens. MTC ON doit donner
# plus de gains convertis, moins de stalls, moins de plies. Si oui → on dépasse Scan (qui n'a pas de MTC).
# expected_duration: ~25 min
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null || true
ART="/root/jass/jobs/results/cpx62-0316-mtc-search-validate/artefacts.src"; mkdir -p "$ART"
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTCDB=/root/egdb_mtc/app
PJTW=/root/jass/jobs/results/cpx62-0311-king-mobility-ab/artefacts.src/endg.pjtw
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente"; exit 4; }
ls "$MTCDB" >/dev/null 2>&1 || { echo "ABORT: MTC absente"; exit 4; }
[ -f "$PJTW" ] || { echo "ABORT: endg.pjtw absent ($PJTW)"; exit 4; }
preflight_build 1 2>/dev/null; preflight_note "2 playouts (n=2000 chacun)" 18 2>/dev/null; preflight_check 2>/dev/null || true

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
cmake --build build-egdb -j"$(mem_safe_jobs 2>/dev/null || echo 4)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 6; }
JASS=/root/jass/build-egdb/jass

echo "############## MTC OFF (ply-only, comportement actuel) ##############"
"$JASS" --egdb-conversion-test "$PJTW" "$WLD" off 2000 12 150 7 2>&1 | tee "$ART/mtc-off.log"
echo; echo "############## MTC ON (distance exacte) ##############"
"$JASS" --egdb-conversion-test "$PJTW" "$WLD" "$MTCDB" 2000 12 150 7 2>&1 | tee "$ART/mtc-on.log"

echo; echo "=========================================================="
echo "   cpx62-0316 — validation MTC-in-search"
echo "----------------------------------------------------------"
echo "  OFF : $(grep -E 'WON within|STALLED|mean plies' "$ART/mtc-off.log" | tr '\n' ' ')"
echo "  ON  : $(grep -E 'WON within|STALLED|mean plies' "$ART/mtc-on.log" | tr '\n' ' ')"
echo "  ON > OFF en WON%, < en STALL% et plies → MTC-in-search valide (à intégrer aux gen/benchmarks"
echo "     via JASS_EGDB_MTC_PATH). Sinon → le -ply suffisait déjà / revoir."
echo "=========================================================="
