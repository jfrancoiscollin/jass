#!/usr/bin/env bash
# id: cpx62-0315-mtc-regret-validate
# description: Valide end-to-end la nouvelle métrique --egdb-mtc-regret (conversion exacte, sans Scan) sur
# un vrai éval 110-extras : endg.pjtw de 0311 (= la couche bakée par défaut). Build egdb-ON, WLD+MTC locaux,
# n=5000 finales gagnantes ≤7p. Confirme que la métrique produit des chiffres sains (préservation-du-gain,
# fastest-path, MTC-regret) avant qu'on bâtisse le run COMBINÉ autour. Auto-contenu.
# expected_duration: ~15 min
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null || true
ART="/root/jass/jobs/results/cpx62-0315-mtc-regret-validate/artefacts.src"; mkdir -p "$ART"
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD=/root/egdb_extracted/app; MTCDB=/root/egdb_mtc/app
PJTW=/root/jass/jobs/results/cpx62-0311-king-mobility-ab/artefacts.src/endg.pjtw
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD egdb absente"; exit 4; }
ls "$MTCDB" >/dev/null 2>&1 || { echo "ABORT: MTC db absente"; exit 4; }
[ -f "$PJTW" ] || { echo "ABORT: endg.pjtw de 0311 absent ($PJTW)"; exit 4; }

preflight_build 1 2>/dev/null; preflight_check 2>/dev/null || true

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
# defaut = JASS_ENDGAME_FEATURES ON (110) → couche identique à endg.pjtw
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 5; }
grep -q "ENDGAME FEATURES ENABLED" "$ART/cmake.log" || echo "WARN: endgame features pas ON ? (vérifier layout pjtw)"
cmake --build build-egdb -j"$(mem_safe_jobs 2>/dev/null || echo 4)" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 6; }
JASS=/root/jass/build-egdb/jass

echo "=== --egdb-mtc-regret sur endg.pjtw (n=5000) ==="
"$JASS" --egdb-mtc-regret "$PJTW" "$WLD" "$MTCDB" 5000 1024 7 2>&1 | tee "$ART/regret.log"

echo; echo "=========================================================="
echo "   cpx62-0315 — validation métrique conversion (--egdb-mtc-regret)"
echo "   Si les 4 chiffres sont sains (préservation ~haute, regret fini) → métrique OK,"
echo "   on l'intègre au run COMBINÉ comme juge de conversion (à la place du endgame_mse)."
echo "=========================================================="
