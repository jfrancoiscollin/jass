#!/usr/bin/env bash
# id: ccx33-0280-egdb-megatools-list
# description: SUITE 0279. apt megatools KO + seulement 27GB libres. Ici : (1) installer un binaire
# megatools STATIQUE depuis GitHub (la boxe atteint github). (2) lister le dossier MEGA WLD 2-7 avec
# TAILLES + total → décide whole-vs-sélectif vu les 27GB. PAS de download des bases (juste le binaire
# ~MB). Ensuite 0281 = download (entier si <~24GB, sinon petites tranches) + build + --egdb-selfcheck.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0280-egdb-megatools-list/artefacts.src"; mkdir -p "$ART"
WLD27="https://mega.nz/#F!vRhFgSjR!bqlaniDcxC65fZWpnovROA"   # WLD 2..7 pieces (folder)

echo "=== (1) binaire megatools statique depuis GitHub releases ==="
mkdir -p /root/mt && cd /root/mt
API="https://api.github.com/repos/megous/megatools/releases/latest"
URL=$(curl -s --max-time 30 "$API" 2>/dev/null \
      | grep -oE '"browser_download_url"[^,]*linux[^,]*x86_64[^,]*"' \
      | grep -oE 'https://[^"]+' | head -1)
[ -z "$URL" ] && URL=$(curl -s --max-time 30 "$API" 2>/dev/null | grep -oE 'https://[^"]+linux[^"]+\.tar\.gz' | head -1)
echo "asset URL: ${URL:-<none found via API>}"
# fallback hardcodé (release statique connue) si l'API ne donne rien
[ -z "$URL" ] && URL="https://github.com/megous/megatools/releases/download/1.11.1.20230212/megatools-1.11.1.20230212-linux-x86_64.tar.gz"
echo "téléchargement: $URL"
curl -sL --max-time 120 "$URL" -o mt.tar.gz 2>"$ART/dl.err" && echo "dl OK ($(wc -c < mt.tar.gz) octets)" || echo "DL FAIL"
tar xzf mt.tar.gz 2>/dev/null || echo "(untar a échoué — format ?)"
MT=$(find /root/mt -maxdepth 3 -name megatools -type f 2>/dev/null | head -1)
[ -z "$MT" ] && MT=$(find /root/mt -maxdepth 3 -name 'megals' -type f 2>/dev/null | head -1)
chmod +x "$MT" 2>/dev/null || true
echo "megatools binaire: ${MT:-INTROUVABLE}"
"$MT" --version 2>&1 | head -1 || true

echo "=== (2) listing du dossier WLD 2-7 (tailles) ==="
if [ -n "$MT" ] && [ -x "$MT" ]; then
  case "$(basename "$MT")" in
    megatools) LS=("$MT" ls -l --reload "$WLD27");;
    megals)    LS=("$MT" -l --reload "$WLD27");;
    *)         LS=("$MT" ls -l "$WLD27");;
  esac
  "${LS[@]}" 2>"$ART/ls.err" | tee "$ART/ls.txt" | head -200
  echo "--- nb lignes: $(wc -l < "$ART/ls.txt" 2>/dev/null || echo 0) ---"
  echo "--- total octets (somme colonne taille si parseable) ---"
  awk '{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+$/ && $i+0>10000){s+=$i; break}} END{printf "  ~%.2f GB\n", s/1073741824}' "$ART/ls.txt" 2>/dev/null || true
  [ -s "$ART/ls.err" ] && { echo "--- ls stderr ---"; head -15 "$ART/ls.err"; }
else
  echo "megatools indisponible — voir dl.err / apt.log."
fi

echo; echo "=========================================================="
echo "   ccx33-0280 — MEGATOOLS (statique) + LISTING TAILLES"
echo "----------------------------------------------------------"
echo "  27GB libres sur la boxe → si total WLD 2-7 < ~24GB : 0281 download ENTIER + selfcheck."
echo "  sinon : 0281 download SÉLECTIF des plus petites tranches (2-4p) + selfcheck."
echo "=========================================================="
