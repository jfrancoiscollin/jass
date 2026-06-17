#!/usr/bin/env bash
# id: home-0004-egdb-install
# description: Installe la bitbase WLD 2-7 sur le PC maison (WSL2) — réplique la chaîne validée des box
# (cpx62-0288), adaptée WSL : garde-fou disque, megatools via apt, build RAM-aware, récupère l'espace de
# l'installeur après extraction. Rend le PC capable des jobs egdb (data-gen finale exacte, mtc-regret,
# conversion-test). WLD seule (~3.5GB dl + ~4.8GB extrait). MTC (2-8, ~29GB) = job séparé si disque ok.
# expected_duration: ~30-90 min (selon le débit internet)
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null || true
ART="/root/jass/jobs/results/home-0004-egdb-install/artefacts.src"; mkdir -p "$ART"
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
DBDIR=/root/egdb_db; EXDIR=/root/egdb_extracted; APP="$EXDIR/app"
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"

echo "=== (0) disque ==="; df -h / | sed 's/^/  /'
AVAIL_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "  libre: ${AVAIL_GB} GB"
if [ "${AVAIL_GB:-0}" -lt 11 ] && ! ls "$APP"/db2.idx1 >/dev/null 2>&1; then
  echo "ABORT: < 11 GB libres — l'install WLD a besoin de ~10 GB (3.5 dl + 4.8 extrait + build)."
  echo "       Libère de la place sur le disque Windows (WSL) puis relance."
  exit 4
fi

echo "=== (1) megatools (apt install, sinon apt download + dpkg-deb) ==="
MT="$(command -v megatools || true)"
if [ -z "$MT" ]; then
  sudo apt-get update -qq >"$ART/apt.log" 2>&1 || true
  sudo apt-get install -y -qq megatools >>"$ART/apt.log" 2>&1 || true
  MT="$(command -v megatools || true)"
fi
if [ -z "$MT" ]; then
  rm -rf /root/mt && mkdir -p /root/mt && cd /root/mt
  apt-get download megatools >>"$ART/apt.log" 2>&1 || echo "apt-get download KO"
  D=$(ls megatools_*.deb 2>/dev/null | head -1); [ -n "$D" ] && dpkg-deb -x "$D" /root/mt/x 2>/dev/null
  MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1); cd /root/jass
fi
chmod +x "$MT" 2>/dev/null || true
"$MT" dl --help >/dev/null 2>&1 && echo "megatools OK ($MT)" || { echo "ABORT: megatools KO"; ldd "$MT" 2>&1 | grep -i 'not found'; exit 5; }

echo "=== (2) download WLD 2-7 (skip si déjà extrait) ==="
if ls "$APP"/db2.idx1 >/dev/null 2>&1; then
  echo "base déjà extraite → skip download+extract"
elif find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | grep -q .; then
  echo "installeur déjà présent → skip download"
else
  mkdir -p "$DBDIR"
  timeout 7200 "$MT" dl --no-progress --path "$DBDIR" "$WLD27" >"$ART/dl.log" 2>&1; echo "  dl rc=$?"
  df -h / | sed 's/^/  after dl /'
fi

if ! ls "$APP"/db2.idx1 >/dev/null 2>&1; then
  SETUP=$(find "$DBDIR" -maxdepth 1 -iname '*Setup*.exe' 2>/dev/null | head -1)
  [ -n "$SETUP" ] || { echo "ABORT: pas d'installeur (download échoué — voir dl.log)"; exit 6; }
  echo "installeur: $SETUP ($(du -sh "$DBDIR" | cut -f1))"
  echo "=== (3) innoextract statique amd64 → $APP ==="
  rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie
  curl -sL --max-time 120 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz && tar xJf ie.tar.xz
  IE=$(find /root/ie -path '*/bin/amd64/innoextract' -type f 2>/dev/null | head -1); chmod +x "$IE" 2>/dev/null || true
  cd /root/jass
  "$IE" --version 2>&1 | head -1 || { echo "ABORT: innoextract KO"; exit 7; }
  rm -rf "$EXDIR"; mkdir -p "$EXDIR"; (cd "$DBDIR" && "$IE" --extract --output-dir "$EXDIR" "$SETUP") >"$ART/inno.log" 2>&1
  echo "  innoextract rc=$?"; tail -3 "$ART/inno.log"
  # récupère l'espace de l'installeur (portable) une fois la base extraite
  ls "$APP"/db2.idx1 >/dev/null 2>&1 && { rm -rf "$DBDIR"; echo "  installeur supprimé (espace récupéré)"; }
fi
ls "$APP"/db2.idx1 "$APP"/db5.idx1 >/dev/null 2>&1 && echo "base OK ($(ls "$APP" | wc -l) fichiers, $(du -sh "$APP" | cut -f1))" || { echo "ABORT: base incomplète"; exit 8; }

echo "=== (4) build JASS_EGDB + self-test natif (autoritaire) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
LIB=/root/jass/build-egdb/libegdb_intl.a
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$(mem_safe_jobs 2>/dev/null || echo 4)" --target jass egdb_intl >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -20 "$ART/build.log"; exit 9; }
cp /root/egdb_intl/example/main.cpp /root/egex.cpp
sed -i 's#C:/db_intl/wld_v2#'"$APP"'#g' /root/egex.cpp
g++ -std=c++17 -O2 -I/root/egdb_intl /root/egex.cpp "$LIB" -lpthread -o /root/egex 2>"$ART/gpp.log" && echo "compile self-test OK" || { echo "COMPILE FAIL"; tail -15 "$ART/gpp.log"; exit 9; }
/root/egex 2>&1 | tee "$ART/selftest.txt" | tail -4
./build-egdb/jass --egdb-selfcheck "$APP" 2000 2>&1 | tail -3

echo; echo "=========================================================="
echo "   home-0004 — bitbase WLD installée sur le PC ($(du -sh "$APP" 2>/dev/null|cut -f1))"
echo "   Self-test natif attendu = 'Test complete, 0 errors.'  → PC prêt pour les jobs egdb."
echo "   (MTC 2-8 ~29GB = job séparé home-0005 si le disque suit.)"
echo "=========================================================="
