#!/usr/bin/env bash
# id: ccx33-0298-mtc-recon
# description: RECON taille MTC 2-8 (pour la cible-gradient (a) : MTC comme cible d'entraînement
# offline → l'éval apprend le gradient de conversion et généralise à 8-21 ; pas de MTC au jeu).
# egdb_intl LIT le MTC (is_mtc, egdb_lookup unifié) — déjà vérifié. Ici on liste le dossier MEGA MTC
# (zFYGVabL) + tailles + df, pour savoir ce qui tient (WLD déjà ~8GB sur disque, ~19GB libres).
# PAS de download des bases (juste le listing). Décide : MTC complet, ou sous-ensemble (≤6/≤7), ou
# faire de la place (virer l'installeur WLD).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0298-mtc-recon/artefacts.src"; mkdir -p "$ART"
MTC="https://mega.nz/#F!zFYGVabL!ZHgOq46KQ_XL8d7z_Zm_PQ"

echo "=== disque ==="; df -h / | sed 's/^/  /'
echo "  occupé par egdb : $(du -sh /root/egdb_db /root/egdb_extracted 2>/dev/null | tr '\n' ' ')"

echo "=== megatools (réutilise /root/mt ou .deb) ==="
MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)
if [ -z "$MT" ]; then
  mkdir -p /root/mt && cd /root/mt && apt-get download megatools >"$ART/apt.log" 2>&1
  D=$(ls megatools_*.deb 2>/dev/null | head -1); [ -n "$D" ] && dpkg-deb -x "$D" /root/mt/x 2>/dev/null
  MT=/root/mt/x/usr/bin/megatools; cd /root/jass
fi
chmod +x "$MT" 2>/dev/null || true
"$MT" dl --help >/dev/null 2>&1 && echo "megatools OK ($MT)" || { echo "ABORT: megatools KO"; exit 5; }

echo "=== listing du dossier MTC 2-8 (noms + tailles) ==="
printf 'q\n' | timeout 150 "$MT" dl --choose-files --path /root/mtc_probe "$MTC" 2>&1 | tee "$ART/mtc-list.txt" | head -100
echo "--- fichiers + tailles repérés ---"
grep -oiE '[0-9.]+ ?[KMG]i?B|[0-9]{6,}|Setup[^ ]*\.(exe|bin)|\.(bin|exe|cpr|idx)' "$ART/mtc-list.txt" 2>/dev/null | head -40

echo; echo "=========================================================="
echo "   ccx33-0298 — RECON taille MTC 2-8"
echo "  voir mtc-list.txt + df ci-dessus."
echo "  SUITE : si total tient (~19GB libres) → download+extract MTC ; sinon sous-ensemble ≤6/≤7"
echo "          ou virer l'installeur WLD (/root/egdb_db, ~3.5GB) pour faire de la place."
echo "=========================================================="
