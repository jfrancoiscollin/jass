#!/usr/bin/env bash
# id: cpx62-0301-cleanup-mtc-download
# description: NETTOIE cpx62 PUIS download+extract MTC 2-8 (miroir de ccx33-0300, pour la cible-gradient
# (a) sur les 2 boxes). S'enchaîne AUTOMATIQUEMENT après 0297 (1 job/boxe, le runner séquence). (1)
# cleanup : vire l'installeur WLD + les artefacts.src des jobs terminés — MAIS GARDE cpx62-0297 (nouveau
# champion gen6 + verdict saturation) ET cpx62-0266 (champion + cumulatif de réf) ET /root/egdb_extracted
# (base WLD) /root/egdb_intl /root/mt. (2) download MTC (~13 GiB). (3) innoextract → /root/egdb_mtc.
# (4) vire l'installeur. (5) liste la structure.
set -uo pipefail
cd /root/jass
MTC="https://mega.nz/#F!zFYGVabL!ZHgOq46KQ_XL8d7z_Zm_PQ"
DL=/root/egdb_mtc_dl; EX=/root/egdb_mtc

echo "=== (1) NETTOYAGE cpx62 (garde champions 0266 + 0297) ==="
df -h / | sed 's/^/  before /'
rm -rf /root/egdb_db 2>/dev/null && echo "  rm /root/egdb_db (installeur WLD)" || true
freed=0
for d in /root/jass/jobs/results/*/artefacts.src; do
  case "$d" in
    *cpx62-0301-cleanup-mtc-download*|*cpx62-0297-saturate-loop*|*cpx62-0266-kingloop-deepplay*) continue;;
  esac
  [ -d "$d" ] && { sz=$(du -sm "$d" 2>/dev/null | cut -f1); freed=$((freed+${sz:-0})); rm -rf "$d"; }
done
echo "  rm artefacts.src jobs terminés (~${freed} MiB ; gardé 0266+0297)"
rm -rf /root/jass/build /root/jass/build-egdb /root/jass/build-prod /root/jass/build-mg /root/jass/build-bd /root/jass/build-prodB /root/jass/build-dist /root/jass/build-flat 2>/dev/null || true
df -h / | sed 's/^/  after-clean /'

echo "=== (2) DOWNLOAD MTC (megatools, ~13 GiB) ==="
MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)
if [ -z "$MT" ]; then
  mkdir -p /root/mt && cd /root/mt && apt-get download megatools >/dev/null 2>&1
  D=$(ls megatools_*.deb 2>/dev/null|head -1); [ -n "$D" ] && dpkg-deb -x "$D" /root/mt/x 2>/dev/null; MT=/root/mt/x/usr/bin/megatools; cd /root/jass
fi
"$MT" dl --help >/dev/null 2>&1 || { echo "ABORT: megatools KO"; exit 5; }
rm -rf "$DL"; mkdir -p "$DL"
timeout 9000 "$MT" dl --no-progress --path "$DL" "$MTC" >/root/mtc-dl.log 2>&1; echo "  dl rc=$?"
du -sh "$DL" 2>/dev/null | sed 's/^/  du DL: /'
SETUP=$(find "$DL" -maxdepth 1 -iname '*Setup*.exe' | head -1)
[ -n "$SETUP" ] || { echo "ABORT: pas d'installeur MTC"; df -h /; tail -5 /root/mtc-dl.log; exit 6; }

echo "=== (3) innoextract → $EX ==="
[ -x /root/ie/innoextract-1.9-linux/bin/amd64/innoextract ] || {
  rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie
  curl -sL --max-time 60 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz && tar xJf ie.tar.xz; cd /root/jass; }
IE=/root/ie/innoextract-1.9-linux/bin/amd64/innoextract; chmod +x "$IE" 2>/dev/null || true
rm -rf "$EX"; mkdir -p "$EX"
(cd "$DL" && "$IE" --extract --output-dir "$EX" "$SETUP") >/root/mtc-inno.log 2>&1; echo "  innoextract rc=$?"; tail -3 /root/mtc-inno.log
du -sh "$EX" 2>/dev/null | sed 's/^/  du extrait: /'

echo "=== (4) vire l'installeur ==="
rm -rf "$DL"; df -h / | sed 's/^/  final /'
echo "=== (5) structure extraite ==="
find "$EX" -maxdepth 2 -type f | head -15
echo "  nb fichiers: $(find "$EX" -type f | wc -l) ; idx/cpr: $(find "$EX" -type f \( -iname '*.idx*' -o -iname '*.cpr*' \) | wc -l)"

echo; echo "=========================================================="
echo "   cpx62-0301 — cpx62 nettoyé + MTC extrait dans $EX (champions 0266+0297 gardés)"
echo "=========================================================="
