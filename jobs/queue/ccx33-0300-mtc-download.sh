#!/usr/bin/env bash
# id: ccx33-0300-mtc-download
# description: NETTOIE ccx33 (disque à 95%) PUIS download+extract le MTC 2-8 (pour la cible-gradient (a)).
# MTC = installeur Inno ~13 GiB (7 .bin) → ~15-18 GiB extrait. (1) cleanup : vire l'installeur WLD
# (/root/egdb_db, 3.5G) + les artefacts.src des jobs TERMINÉS (data self-play, dumps featM) — libère
# ~100+ GiB. GARDE /root/egdb_extracted (base WLD), /root/egdb_intl, /root/mt. (2) megatools dl le
# dossier MEGA MTC. (3) innoextract → /root/egdb_mtc. (4) vire l'installeur. (5) liste la structure
# extraite (db*.idx/cpr MTC). La sonde MTC dans le bridge + la labellisation-gradient = étape suivante.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
MTC="https://mega.nz/#F!zFYGVabL!ZHgOq46KQ_XL8d7z_Zm_PQ"
DL=/root/egdb_mtc_dl; EX=/root/egdb_mtc

echo "=== (1) NETTOYAGE ccx33 ==="
df -h / | sed 's/^/  before /'
# installeur WLD (on a l'extrait)
rm -rf /root/egdb_db && echo "  rm /root/egdb_db (installeur WLD)"
# artefacts.src des jobs TERMINÉS (sauf le job courant) — gros de la data self-play
freed=0
for d in /root/jass/jobs/results/*/artefacts.src; do
  case "$d" in *ccx33-0300-mtc-download*) continue;; esac
  [ -d "$d" ] && { sz=$(du -sm "$d" 2>/dev/null | cut -f1); freed=$((freed+${sz:-0})); rm -rf "$d"; }
done
echo "  rm artefacts.src jobs terminés (~${freed} MiB)"
# caches build régénérables
rm -rf /root/jass/build /root/jass/build-egdb /root/jass/build-prod /root/jass/build-mg 2>/dev/null || true
df -h / | sed 's/^/  after-clean /'

echo "=== (2) DOWNLOAD MTC (megatools, ~13 GiB) ==="
MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)
[ -n "$MT" ] || { echo "ABORT: megatools introuvable"; exit 5; }
rm -rf "$DL"; mkdir -p "$DL"
timeout 7200 "$MT" dl --no-progress --path "$DL" "$MTC" >/root/mtc-dl.log 2>&1; echo "  dl rc=$?"
ls -la "$DL" | sed 's/^/  /'; echo "  du: $(du -sh "$DL" | cut -f1)"
SETUP=$(find "$DL" -maxdepth 1 -iname '*Setup*.exe' | head -1)
[ -n "$SETUP" ] || { echo "ABORT: pas d'installeur MTC"; df -h /; exit 6; }

echo "=== (3) innoextract (statique amd64) → $EX ==="
[ -x /root/ie/innoextract-1.9-linux/bin/amd64/innoextract ] || {
  rm -rf /root/ie && mkdir -p /root/ie && cd /root/ie
  curl -sL --max-time 60 "https://github.com/dscharrer/innoextract/releases/download/1.9/innoextract-1.9-linux.tar.xz" -o ie.tar.xz && tar xJf ie.tar.xz; cd /root/jass; }
IE=/root/ie/innoextract-1.9-linux/bin/amd64/innoextract; chmod +x "$IE" 2>/dev/null || true
rm -rf "$EX"; mkdir -p "$EX"
(cd "$DL" && "$IE" --extract --output-dir "$EX" "$SETUP") >/root/mtc-inno.log 2>&1; echo "  innoextract rc=$?"; tail -3 /root/mtc-inno.log
echo "  du extrait: $(du -sh "$EX" | cut -f1)"

echo "=== (4) vire l'installeur (libère ~13 GiB) ==="
rm -rf "$DL"; df -h / | sed 's/^/  final /'

echo "=== (5) structure extraite MTC ==="
find "$EX" -maxdepth 2 -type f | head -20
echo "  nb fichiers: $(find "$EX" -type f | wc -l)  ; idx/cpr: $(find "$EX" -type f \( -iname '*.idx*' -o -iname '*.cpr*' \) | wc -l)"

echo; echo "=========================================================="
echo "   ccx33-0300 — MTC téléchargé + extrait dans $EX"
echo "   SUITE : sonde MTC dans egdb_bridge (egdb_open MTC + is_mtc + lookup) + outil de"
echo "           labellisation-gradient (position ≤8 → distance MTC → cible graduée)."
echo "=========================================================="
