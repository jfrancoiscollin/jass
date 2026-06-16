#!/usr/bin/env bash
# id: ccx33-0299-mtc-recon-fix
# description: RECON MTC corrigée (0298 : oubli du mkdir du dossier-sonde → listing échoué ; et disque
# ccx33 à 7.2GB libres seulement). Ici : mkdir + liste le dossier MEGA MTC 2-8 (noms + TAILLES) +
# rapporte l'espace libérable (installeur WLD /root/egdb_db ~3.5GB, /root/mt, builds). Décide :
# MTC complet (improbable vu le disque) vs sous-ensemble ≤6/≤7 vs faire de la place vs autre boxe.
# PAS de download des bases.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0299-mtc-recon-fix/artefacts.src"; mkdir -p "$ART"
MTC="https://mega.nz/#F!zFYGVabL!ZHgOq46KQ_XL8d7z_Zm_PQ"

echo "=== disque + espace libérable ==="
df -h / | sed 's/^/  /'
echo "  /root/egdb_db (installeur WLD, supprimable) : $(du -sh /root/egdb_db 2>/dev/null | cut -f1)"
echo "  /root/egdb_extracted (base WLD, À GARDER)   : $(du -sh /root/egdb_extracted 2>/dev/null | cut -f1)"
echo "  builds jass (build*, regénérables)          : $(du -sh /root/jass/build* 2>/dev/null | tail -1 | cut -f1)"

MT=$(find /root/mt -path '*/usr/bin/megatools' -type f 2>/dev/null | head -1)
[ -n "$MT" ] && echo "megatools: $MT" || { echo "ABORT: megatools introuvable"; exit 5; }

echo "=== listing MTC 2-8 (mkdir d'abord cette fois) ==="
mkdir -p /root/mtc_probe
printf 'q\n' | timeout 180 "$MT" dl --choose-files --path /root/mtc_probe "$MTC" 2>&1 | tee "$ART/mtc-list.txt" | head -120
echo "--- lignes : $(wc -l < "$ART/mtc-list.txt" 2>/dev/null || echo 0) ---"
echo "--- fichiers + tailles (Setup/.bin/.exe + nombres) ---"
grep -oiE 'Setup[^ ]*|[0-9]+ ?[KMG]i?B|[0-9]{7,}' "$ART/mtc-list.txt" 2>/dev/null | head -40

echo; echo "=========================================================="
echo "   ccx33-0299 — RECON MTC (corrigée)"
echo "  taille MTC ci-dessus vs ~7.2GB libres (+3.5GB si on vire l'installeur WLD)."
echo "  SUITE : choisir MTC complet / sous-ensemble ≤6-7 / libérer / autre boxe."
echo "=========================================================="
