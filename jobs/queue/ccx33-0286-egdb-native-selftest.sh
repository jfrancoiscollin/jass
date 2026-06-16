#!/usr/bin/env bash
# id: ccx33-0286-egdb-native-selftest
# description: VALIDATION AUTORITAIRE de la bitbase. Le selfcheck 0285 a flaggé "BUG" mais c'était un
# faux alarme : il comparait egdb à NOS tables internes (heuristique courte, pas une vérité). Preuve
# hors-ligne : ma conversion jass→egdb reproduit au bit près les positions d'exemple egdb (homme+roi
# asymétrique décisif). Ici on tranche pour de bon : on compile et lance le SELF-TEST NATIF d'egdb_intl
# (example/main.cpp, ~140 positions à WLD connu, RAW egdb, zéro jass) contre la base téléchargée. "0
# errors" = egdb_lookup + base + format = OK → bitbase scellée, intégrable. (Base extraite persiste
# dans /root/egdb_extracted/app.)
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0286-egdb-native-selftest/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
APP=/root/egdb_extracted/app

echo "=== base présente ? ==="
ls "$APP"/db2.idx1 "$APP"/db5.idx1 >/dev/null 2>&1 && echo "OK base extraite ($(ls "$APP" | wc -l) fichiers)" || { echo "ABORT: base absente dans $APP"; exit 0; }

echo "=== lib egdb_intl (réutilise le build jass si présent, sinon build) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
LIB=/root/jass/build-egdb/libegdb_intl.a
if [ ! -f "$LIB" ]; then
  cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
  cmake --build build-egdb -j"$NCPU" --target egdb_intl >"$ART/buildlib.log" 2>&1
fi
[ -f "$LIB" ] && echo "lib OK: $LIB" || { echo "ABORT: lib egdb introuvable"; tail -10 "$ART/buildlib.log" 2>/dev/null; exit 0; }

echo "=== compile le self-test natif (example/main.cpp, DB_PATH→base, maxpieces inchangé=6) ==="
cp /root/egdb_intl/example/main.cpp /root/egex.cpp
# remplace le chemin Windows hardcodé par notre dossier
sed -i 's#C:/db_intl/wld_v2#'"$APP"'#g' /root/egex.cpp
grep -n 'egdb_open\|DB_PATH' /root/egex.cpp | head
g++ -std=c++17 -O2 -I/root/egdb_intl /root/egex.cpp "$LIB" -lpthread -o /root/egex 2>"$ART/gpp.log" \
  && echo "compile OK" || { echo "COMPILE FAIL"; tail -20 "$ART/gpp.log"; exit 0; }

echo "=== RUN self-test natif egdb ==="
/root/egex 2>&1 | tee "$ART/selftest.txt" | tail -25

echo; echo "=========================================================="
echo "   ccx33-0286 — SELF-TEST NATIF EGDB (autoritaire)"
echo "----------------------------------------------------------"
echo "  'Test complete, 0 errors.' → egdb_lookup + base + format VALIDÉS (indépendant de jass)."
echo "  → combiné à la conversion validée hors-ligne = BITBASE SCELLÉE, prête à intégrer."
echo "  (erreurs > 0 → vrai problème base/format, on creuse.)"
echo "=========================================================="
