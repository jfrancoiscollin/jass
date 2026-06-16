#!/usr/bin/env bash
# id: cpx62-0288-egdb-prep
# description: PREP bitbase sur cpx62 (ubuntu-32gb-hel1-1) — il n'a pas la base (seul ccx33 l'a). Rejoue
# la chaîne VALIDÉE sur ccx33 (jobs 0282/0284/0286), self-contained + idempotent : (1) megatools via
# apt-get download + dpkg-deb -x. (2) download MEGA WLD 2-7 (installeur Inno Setup ~3.5GB) → /root/egdb_db.
# (3) innoextract STATIQUE amd64 (GitHub) → /root/egdb_extracted/app (db2…db7-NNNN, ~4.8GB). (4) build
# JASS_EGDB + SELF-TEST NATIF egdb (example/main.cpp, ~164 positions) → DOIT être "0 errors". Rend cpx62
# capable de tourner les jobs egdb (relabel/scaling) en parallèle de ccx33.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0288-egdb-prep/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DBDIR=/root/egdb_db; EXDIR=/root/egdb_extracted; APP="$EXDIR/app"
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"

echo "=== (0) disque ==="; df -h / | sed 's/^/  /'

echo "=== (1) megatools (.deb Ubuntu, dpkg-deb -x) ==="
MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)
if [ -z "$MT" ]; then
  rm -rf /root/mt && mkdir -p /root/mt && cd /root/mt
  apt-get download megatools >"$ART/apt.log" 2>&1 || echo "apt-get download KO (voir apt.log)"
  D=$(ls megatools_*.deb 2>/dev/null | head -1); [ -n "$D" ] && dpkg-deb -x "$D" /root/mt/x 2>/dev/null
  MT=/root/mt/x/usr/bin/megatools; cd /root/jass
fi
chmod +x "$MT" 2>/dev/null || true
"$MT" dl --help >/dev/null 2>&1 && echo "megatools OK" || { echo "ABORT: megatools KO"; ldd "$MT" 2>&1 | grep -i 'not found'; exit 5; }

echo "=== (2) download WLD 2-7 (skip si déjà là) ==="
if find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | grep -q .; then
  echo "installeur déjà présent → skip download"
else
  mkdir -p "$DBDIR"
  df -h / | sed 's/^/  before /'
  timeout 5400 "$MT" dl --no-progress --path "$DBDIR" "$WLD27" >"$ART/dl.log" 2>&1; echo "  dl rc=$?"
  df -h / | sed 's/^/  after  /'
fi
SETUP=$(find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | head -1)
[ -n "$SETUP" ] && echo "installeur: $SETUP ($(du -sh "$DBDIR" | cut -f1))" || { echo "ABORT: pas d'installeur"; exit 6; }

echo "=== (3) innoextract statique amd64 → extraction (skip si déjà fait) ==="
if ls "$APP"/db*.idx1 >/dev/null 2>&1; then
  echo "déjà extrait ($(ls "$APP"/db*.idx1 | wc -l) idx1) → skip"
else
  rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie
  curl -sL --max-time 60 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz && tar xJf ie.tar.xz
  IE=$(find /root/ie -path '*/bin/amd64/innoextract' -type f 2>/dev/null | head -1); chmod +x "$IE" 2>/dev/null || true
  cd /root/jass
  "$IE" --version 2>&1 | head -1 || { echo "ABORT: innoextract KO"; exit 7; }
  rm -rf "$EXDIR"; mkdir -p "$EXDIR"; (cd "$DBDIR" && "$IE" --extract --output-dir "$EXDIR" "$SETUP") >"$ART/inno.log" 2>&1
  echo "  innoextract rc=$?"; tail -3 "$ART/inno.log"
fi
ls "$APP"/db2.idx1 "$APP"/db5.idx1 >/dev/null 2>&1 && echo "base OK ($(ls "$APP" | wc -l) fichiers, $(du -sh "$APP" | cut -f1))" || { echo "ABORT: base incomplète"; exit 8; }

echo "=== (4) build JASS_EGDB + self-test natif (autoritaire) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
LIB=/root/jass/build-egdb/libegdb_intl.a
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass egdb_intl >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -20 "$ART/build.log"; exit 9; }
cp /root/egdb_intl/example/main.cpp /root/egex.cpp
sed -i 's#C:/db_intl/wld_v2#'"$APP"'#g' /root/egex.cpp
g++ -std=c++17 -O2 -I/root/egdb_intl /root/egex.cpp "$LIB" -lpthread -o /root/egex 2>"$ART/gpp.log" && echo "compile self-test OK" || { echo "COMPILE FAIL"; tail -15 "$ART/gpp.log"; exit 9; }
/root/egex 2>&1 | tee "$ART/selftest.txt" | tail -4
# jass-side pré-vol aussi (invariant)
./build-egdb/jass --egdb-selfcheck "$APP" 2000 2>&1 | tail -3

echo; echo "=========================================================="
echo "   cpx62-0288 — PREP BITBASE (cpx62 prêt pour egdb)"
echo "----------------------------------------------------------"
echo "  base : $APP   (self-test natif egdb attendu = 'Test complete, 0 errors.')"
echo "  → cpx62 peut désormais tourner les jobs egdb en parallèle de ccx33."
echo "=========================================================="
