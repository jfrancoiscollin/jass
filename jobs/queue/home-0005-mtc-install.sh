#!/usr/bin/env bash
# id: home-0005-mtc-install
# description: Installe la DB MTC 2-8 (moves-to-conversion) sur le PC maison — complète home-0004 (WLD).
# Nécessaire pour --egdb-mtc-regret / --egdb-conversion-test / MTC-in-search. Réutilise megatools +
# innoextract déjà posés par home-0004. download ~13 Go → innoextract → /root/egdb_mtc/app (~29 Go) →
# vire l'installeur → vérif --egdb-mtc-probe. Disque OK (947 Go libres au home-0004).
# expected_duration: ~40-120 min (selon débit internet)
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null || true
ART="/root/jass/jobs/results/home-0005-mtc-install/artefacts.src"; mkdir -p "$ART"
MTC="https://mega.nz/#F!zFYGVabL!ZHgOq46KQ_XL8d7z_Zm_PQ"
DL=/root/egdb_mtc_dl; EX=/root/egdb_mtc; WLD=/root/egdb_extracted/app
ls "$WLD"/db2.idx1 >/dev/null 2>&1 || { echo "ABORT: WLD absente — lance home-0004 d'abord"; exit 4; }

echo "=== (0) disque ==="; df -h / | sed 's/^/  /'
AVAIL_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
if [ "${AVAIL_GB:-0}" -lt 45 ] && ! find "$EX" -iname '*.idx*' 2>/dev/null | grep -q .; then
  echo "ABORT: < 45 GB libres — le MTC a besoin de ~13 dl + ~29 extrait."; exit 4
fi

if find "$EX" -type f \( -iname '*.idx*' -o -iname '*.cpr*' \) 2>/dev/null | grep -q .; then
  echo "MTC déjà extrait → skip download"
else
  echo "=== (1) megatools ==="
  MT="$(command -v megatools || find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)"
  [ -z "$MT" ] && { sudo apt-get install -y -qq megatools >"$ART/apt.log" 2>&1 || true; MT="$(command -v megatools || true)"; }
  "$MT" dl --help >/dev/null 2>&1 || { echo "ABORT: megatools KO"; exit 5; }

  echo "=== (2) download MTC (~13 Go) ==="
  rm -rf "$DL"; mkdir -p "$DL"
  timeout 12000 "$MT" dl --no-progress --path "$DL" "$MTC" >"$ART/dl.log" 2>&1; echo "  dl rc=$?"
  du -sh "$DL" 2>/dev/null | sed 's/^/  du DL: /'
  SETUP=$(find "$DL" -maxdepth 1 -iname '*Setup*.exe' | head -1)
  [ -n "$SETUP" ] || { echo "ABORT: pas d'installeur MTC"; tail -5 "$ART/dl.log"; df -h /; exit 6; }

  echo "=== (3) innoextract → $EX ==="
  IE=/root/ie/innoextract-1.9-linux/bin/amd64/innoextract
  [ -x "$IE" ] || { rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie && \
     curl -sL --max-time 120 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz && tar xJf ie.tar.xz; cd /root/jass; }
  chmod +x "$IE" 2>/dev/null || true
  rm -rf "$EX"; mkdir -p "$EX"
  (cd "$DL" && "$IE" --extract --output-dir "$EX" "$SETUP") >"$ART/inno.log" 2>&1; echo "  innoextract rc=$?"; tail -3 "$ART/inno.log"
  rm -rf "$DL"; echo "  installeur MTC supprimé"
fi
du -sh "$EX" 2>/dev/null | sed 's/^/  du MTC extrait: /'
echo "  idx/cpr: $(find "$EX" -type f \( -iname '*.idx*' -o -iname '*.cpr*' \) | wc -l)"

echo "=== (4) vérif lecture MTC (--egdb-mtc-probe) ==="
JASS=/root/jass/build-egdb/jass
[ -x "$JASS" ] || { echo "(build-egdb absent — rebuild)"; cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl >"$ART/cmake.log" 2>&1 && cmake --build build-egdb -j"$(mem_safe_jobs 2>/dev/null||echo 4)" --target jass >"$ART/build.log" 2>&1; }
"$JASS" --egdb-mtc-probe "$WLD" "$EX/app" 20000 1024 2>&1 | tail -6

echo; echo "=========================================================="
echo "   home-0005 — MTC installé sur le PC ($(du -sh "$EX/app" 2>/dev/null|cut -f1))"
echo "   PC prêt pour --egdb-mtc-regret / --egdb-conversion-test / MTC-in-search."
echo "=========================================================="
