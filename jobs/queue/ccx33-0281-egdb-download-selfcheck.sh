#!/usr/bin/env bash
# id: ccx33-0281-egdb-download-selfcheck
# description: SUITE 0280. megatools via .deb Ubuntu (apt KO ; static GitHub KO). Plan : (1) megatools
# depuis le .deb universe correspondant au codename de la boxe (les libs glib/curl/ssl sont déjà là),
# extrait par dpkg-deb -x (pas d'install). (2) LISTER le dossier MEGA WLD 2-7 via `dl --choose-files`
# (le `ls` ne marche pas sur les liens dossier publics) → noms + tailles. (3) si ça tient dans les
# 27GB, TÉLÉCHARGER tout le dossier 2-7 (sinon on verra au df). (4) build JASS_EGDB + JASS_EGDB_PATH
# → `jass --egdb-selfcheck` qui DOIT être CLEAN (KvK=Draw, gains définis == nos tables). Diagnostics
# à chaque étape (ldd, df, du, head).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0281-egdb-download-selfcheck/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"
DBDIR=/root/egdb_db

echo "=== (1) megatools via .deb Ubuntu (codename-matched) ==="
. /etc/os-release 2>/dev/null || true
echo "  box: ${PRETTY_NAME:-?}  codename=${VERSION_CODENAME:-?}"
POOL="http://archive.ubuntu.com/ubuntu/pool/universe/m/megatools"
case "${VERSION_CODENAME:-}" in
  noble)  DEB=megatools_1.11.5-1build1_amd64.deb;;
  jammy)  DEB=megatools_1.11.1-1build3_amd64.deb;;
  focal)  DEB=megatools_1.10.3-1build1_amd64.deb;;
  *)      DEB=megatools_1.11.1-1build3_amd64.deb;;   # generic fallback
esac
rm -rf /root/mt && mkdir -p /root/mt && cd /root/mt
# prefer apt-get download (no install) ; fallback to the pool .deb
( apt-get download megatools ) >"$ART/aptget.log" 2>&1 && echo "apt-get download OK" || \
  { echo "apt-get download KO → pool $DEB"; curl -sL --max-time 90 "$POOL/$DEB" -o mt.deb && echo "pool dl $(wc -c < mt.deb) o"; }
DEBFILE=$(ls megatools_*.deb 2>/dev/null | head -1); [ -z "$DEBFILE" ] && DEBFILE=mt.deb
dpkg-deb -x "$DEBFILE" /root/mt/x 2>/dev/null && echo "extrait"
MT=/root/mt/x/usr/bin/megatools; chmod +x "$MT" 2>/dev/null || true
cd /root/jass
echo "  ldd megatools:"; ldd "$MT" 2>&1 | grep -iE 'not found|=>' | head -12
echo "  version:"; "$MT" --version 2>&1 | head -1 || echo "  (megatools ne tourne pas)"
"$MT" --version >/dev/null 2>&1 || { echo "ABORT: megatools inutilisable (libs manquantes ci-dessus)"; exit 0; }

echo "=== (2) listing du dossier WLD 2-7 (dl --choose-files, EOF→print&abort) ==="
printf 'q\n' | timeout 120 "$MT" dl --choose-files --path "$DBDIR" "$WLD27" 2>&1 | tee "$ART/choose.txt" | head -80 || true
echo "  (lignes: $(wc -l < "$ART/choose.txt" 2>/dev/null || echo 0))"

echo "=== (3) download du dossier WLD 2-7 ==="
df -h / | sed 's/^/  before /'
mkdir -p "$DBDIR"
timeout 5400 "$MT" dl --no-progress --path "$DBDIR" "$WLD27" >"$ART/dl.log" 2>&1; DLRC=$?
echo "  dl rc=$DLRC (124=timeout)"; tail -4 "$ART/dl.log"
df -h / | sed 's/^/  after  /'
echo "  du -sh $DBDIR : $(du -sh "$DBDIR" 2>/dev/null | cut -f1)"
echo "  arborescence (≤2 niveaux) :"; find "$DBDIR" -maxdepth 2 2>/dev/null | head -40

echo "=== (4) build JASS_EGDB + selfcheck ==="
rm -rf /root/egdb_intl; git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1 && echo "clone OK"
rm -rf build-egdb
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1
cmake --build build-egdb -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -20 "$ART/build.log"; exit 0; }
# point egdb at the directory that actually contains the db files
DBROOT=$(dirname "$(find "$DBDIR" -maxdepth 3 -type f \( -iname '*.idx' -o -iname '*.cpr' -o -iname '*.bin' \) 2>/dev/null | head -1)")
[ -z "$DBROOT" ] && DBROOT="$DBDIR"
echo "  DBROOT=$DBROOT"; ls -la "$DBROOT" 2>/dev/null | head -15
echo "--- selfcheck (200k positions) ---"
./build-egdb/jass --egdb-selfcheck "$DBROOT" 200000 2>&1 | tee "$ART/selfcheck.txt" | tail -20

echo; echo "=========================================================="
echo "   ccx33-0281 — DOWNLOAD WLD 2-7 + SELFCHECK"
echo "----------------------------------------------------------"
echo "  selfcheck : voir 'RESULT: CLEAN' (mapping validé) ou 'BUG'."
echo "  CLEAN → on intègre la bitbase (probe en finale) + on l'utilise pour relabeliser les finales."
echo "=========================================================="
