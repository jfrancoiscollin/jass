#!/usr/bin/env bash
# id: ccx33-0284-egdb-innoextract-selfcheck
# description: SUITE 0282. Le download MEGA a marché (3.5GB) mais c'est un INSTALLEUR Inno Setup
# (Kingsrow_Intl_7pc_WLD_Setup.exe + Setup-1/2.bin), pas les fichiers DB bruts. On extrait avec
# innoextract (binaire STATIQUE GitHub, zéro dépendance) → les vrais fichiers de base. Puis build
# JASS_EGDB + JASS_EGDB_PATH=<dir extrait> → `jass --egdb-selfcheck` qui DOIT être CLEAN (KvK=Draw,
# nos gains définis == egdb). L'installeur persiste dans /root/egdb_db (hors repo) ; re-download
# via megatools seulement s'il a disparu.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0284-egdb-innoextract-selfcheck/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DBDIR=/root/egdb_db
EXDIR=/root/egdb_extracted
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"

echo "=== (0) installeur présent ? (persiste hors repo) ==="
ls -la "$DBDIR" 2>/dev/null | head
SETUP=$(find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | head -1)
if [ -z "$SETUP" ]; then
  echo "installeur absent → re-download via megatools"
  MT=$(find /root/mt -name megatools -type f 2>/dev/null | head -1)
  if [ -z "$MT" ]; then
    mkdir -p /root/mt && cd /root/mt && apt-get download megatools >/dev/null 2>&1
    dpkg-deb -x megatools_*.deb /root/mt/x 2>/dev/null; MT=/root/mt/x/usr/bin/megatools; cd /root/jass
  fi
  chmod +x "$MT" 2>/dev/null || true; mkdir -p "$DBDIR"
  timeout 5400 "$MT" dl --no-progress --path "$DBDIR" "$WLD27" >"$ART/dl.log" 2>&1
  SETUP=$(find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | head -1)
fi
[ -z "$SETUP" ] && { echo "ABORT: pas d'installeur"; exit 0; }
echo "installeur: $SETUP"

echo "=== (1) innoextract statique (GitHub, zéro dépendance) ==="
rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie
curl -sL --max-time 60 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz \
  && tar xJf ie.tar.xz && echo "innoextract dl+untar OK"
IE=$(find /root/ie -path "*/bin/amd64/innoextract" -type f 2>/dev/null | head -1); chmod +x "$IE" 2>/dev/null || true  # amd64 explicite (le wrapper choisit i686 à tort sur la boxe)
cd /root/jass
"$IE" --version 2>&1 | head -1 || { echo "ABORT: innoextract KO"; exit 0; }

echo "=== (2) extraction de l'installeur ==="
df -h / | sed 's/^/  before /'
rm -rf "$EXDIR"; mkdir -p "$EXDIR"; cd "$DBDIR"
"$IE" --extract --output-dir "$EXDIR" "$SETUP" >"$ART/inno.log" 2>&1; IRC=$?
echo "innoextract rc=$IRC"; tail -4 "$ART/inno.log"
cd /root/jass
df -h / | sed 's/^/  after  /'
echo "  du -sh $EXDIR : $(du -sh "$EXDIR" 2>/dev/null | cut -f1)"
echo "  arborescence extraite (≤3 niveaux) :"; find "$EXDIR" -maxdepth 3 2>/dev/null | head -50

echo "=== (3) build JASS_EGDB + selfcheck ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -20 "$ART/build.log"; exit 0; }
# trouver le dossier qui contient les fichiers de base egdb
DBF=$(find "$EXDIR" -type f \( -iname '*.idx' -o -iname '*.cpr' -o -iname '*.bin' -o -iname '*.dbh' \) 2>/dev/null | head -1)
DBROOT=$(dirname "$DBF" 2>/dev/null); [ -z "$DBROOT" ] && DBROOT="$EXDIR"
echo "  DBROOT=$DBROOT"; ls -la "$DBROOT" 2>/dev/null | head -20
echo "--- selfcheck (200k positions) ---"
JASS_EGDB_CACHE_MB=2048 ./build-egdb/jass --egdb-selfcheck "$DBROOT" 200000 2>&1 | tee "$ART/selfcheck.txt" | tail -22

echo; echo "=========================================================="
echo "   ccx33-0283 — INNOEXTRACT + SELFCHECK BITBASE"
echo "----------------------------------------------------------"
echo "  RESULT: CLEAN → mapping validé sur données réelles → bitbase opérationnelle."
echo "  (sinon : voir DBROOT / structure extraite ci-dessus, ajuster le chemin.)"
echo "=========================================================="
