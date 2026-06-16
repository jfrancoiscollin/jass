#!/usr/bin/env bash
# id: ccx33-0279-egdb-mega-recon
# description: SUITE 0278. Acquis : build JASS_EGDB OK sur la boxe ; bases hébergées sur MEGA (liens
# DOSSIER mega.nz/#F!...). Le selfcheck n'a besoin que des tranches 2-4 pièces (KvK/2v1/3v1) → il
# FAUT télécharger sélectivement, pas tout le dossier 2-7 (potentiellement énorme). RECON d'abord :
# (1) installer megatools (apt, fallback build/binaire). (2) megals -l du dossier WLD 2-7 → noms +
# TAILLES des fichiers (pour repérer les petites tranches). (3) df -h (place dispo). (4) reachability
# mega.nz. PAS de gros download ici. Ensuite je code 0280 = download sélectif tranches ≤4-6p + --egdb-
# selfcheck (doit être CLEAN).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0279-egdb-mega-recon/artefacts.src"; mkdir -p "$ART"
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"   # WLD 2..7 pieces (folder)

echo "=== (0) place disque + reachability mega.nz ==="
df -h / /root /tmp 2>/dev/null | sed 's/^/  /'
echo "mega.nz HEAD: $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://mega.nz/ 2>/dev/null)"

echo "=== (1) installer megatools ==="
if command -v megatools >/dev/null 2>&1 || command -v megals >/dev/null 2>&1 || command -v megadl >/dev/null 2>&1; then
  echo "megatools déjà présent"
else
  (sudo apt-get update -y && sudo apt-get install -y megatools) >"$ART/apt.log" 2>&1 \
    || (apt-get update -y && apt-get install -y megatools) >>"$ART/apt.log" 2>&1 \
    || echo "apt megatools FAIL (voir apt.log)"
fi
# resolve a working list + download command (megatools renamed subcommands across versions)
MEGALS=""; MEGADL=""
command -v megals  >/dev/null 2>&1 && MEGALS="megals"
command -v megadl  >/dev/null 2>&1 && MEGADL="megadl"
if [ -z "$MEGALS" ] && command -v megatools >/dev/null 2>&1; then MEGALS="megatools ls"; MEGADL="megatools dl"; fi
echo "  megals='$MEGALS'  megadl='$MEGADL'  ($(megatools --version 2>/dev/null | head -1 || echo 'version?'))"

echo "=== (2) listing du dossier WLD 2-7 (noms + tailles) ==="
if [ -n "$MEGALS" ]; then
  $MEGALS -l "$WLD27" 2>"$ART/megals.err" | tee "$ART/megals.txt" | head -120
  echo "  (total lignes: $(wc -l < "$ART/megals.txt" 2>/dev/null || echo 0))"
  echo "--- fichiers qui ressemblent aux PETITES tranches (db2/db3/db4, *.idx, *.cpr, 2..4) ---"
  grep -iE 'db0?[234]|/[234][^0-9]|\.idx|\.cpr|2pc|3pc|4pc' "$ART/megals.txt" 2>/dev/null | head -40
  [ -s "$ART/megals.err" ] && { echo "--- megals stderr ---"; head -10 "$ART/megals.err"; }
else
  echo "megatools indisponible → impossible de lister. Fallback à étudier (megacmd / mega.py)."
fi

echo; echo "=========================================================="
echo "   ccx33-0279 — RECON MEGA (tailles des tranches WLD)"
echo "----------------------------------------------------------"
echo "  disque + mega reachability + listing ci-dessus."
echo "  SUITE 0280 : megadl SÉLECTIF des tranches ≤4-6 pièces vers /root/egdb_db,"
echo "               build JASS_EGDB, JASS_EGDB_PATH=/root/egdb_db jass --egdb-selfcheck (CLEAN requis)."
echo "=========================================================="
