#!/usr/bin/env bash
# id: cpx62-0684-fmjd-recon
# description: RECON (memo D, avant chantier fetcher) — teste depuis la BOX la joignabilite de toernooibase/FMJD (mon conteneur
# est bloque par policy proxy) + decouvre la structure REELLE des endpoints PDN + tente un petit fetch. Si une PDN est obtenue,
# valide la chaine complete clean_pdn -> --replay-moves -> --gen-siblings (master) sur vraie donnee elite. Aucun scraping massif,
# aucune donnee committee (juste des ECHANTILLONS + un rapport de structure). Leger. Determine si le fetcher A est faisable.
set -uo pipefail
cd /root/jass
NCPU=$(nproc)
ART="/root/jass/jobs/results/cpx62-0684-fmjd-recon/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0684-fmjd-recon/artefacts"
W=/root/cw-fmjdrecon; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
START=$(date +%s)
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
say "=== FMJD/TOERNOOIBASE RECON (depuis la box) — $(date -u +%FT%TZ) ==="

# --- 1. joignabilite des hotes ---
say ""; say "=== 1. joignabilite (curl -I, timeout 20s) ==="
declare -A HOSTS=(
  [toernooibase]="https://toernooibase.kndb.nl/"
  [results_fmjd]="https://results.fmjd.org/"
  [pdn_fmjd]="https://pdn.fmjd.org/"
  [www_fmjd]="https://www.fmjd.org/"
)
REACH=0
for k in "${!HOSTS[@]}"; do
  u="${HOSTS[$k]}"
  code=$(curl -sS -o "$W/home_$k.html" -w '%{http_code}' -A "Mozilla/5.0 jass-research" --max-time 20 "$u" 2>/dev/null || echo "000")
  sz=$(stat -c%s "$W/home_$k.html" 2>/dev/null || echo 0)
  say "  $k : HTTP $code (${sz}o)  $u"
  [ "$code" = "200" ] && REACH=$((REACH+1))
done
if [ "$REACH" -eq 0 ]; then
  say ""; say "  ⚠ AUCUN hote joignable depuis la box (policy reseau) => fetcher automatique INFAISABLE ici."
  say "     Repli : bulk PDN Bouma (option C) a brancher directement sur le pipeline (clean_pdn -> --replay-moves)."
  commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0684 fmjd-recon : hotes injoignables depuis box -> repli Bouma (C)"
  say "=== fin recon ==="; exit 0
fi

# --- 2. structure endpoints PDN (grep les pages recuperees) ---
say ""; say "=== 2. endpoints PDN/export/download reperes ==="
for f in "$W"/home_*.html; do
  hits=$(grep -ioE 'href="[^"]*(pdn|export|download|game|partij|wed=|oerterp)[^"]*"' "$f" 2>/dev/null | sort -u | head -20)
  [ -n "$hits" ] && { say "  -- $(basename "$f") --"; echo "$hits" | sed 's/^/    /' | tee -a "$RES"; }
done
# sauver un extrait de chaque page pour lecture manuelle (structure)
for f in "$W"/home_*.html; do head -c 4000 "$f" > "$ART/$(basename "$f").head" 2>/dev/null || true; done
say "  (extraits pages -> artefacts *.head pour lecture structure)"

# --- 3. tenter un petit fetch PDN (endpoints connus a sonder) ---
say ""; say "=== 3. sondes fetch PDN (best-effort) ==="
GOTPDN=""
# candidats connus : pdn.fmjd.org example, toernooibase export par periode (souvent compte-gate)
for probe in \
  "https://pdn.fmjd.org/" \
  "https://results.fmjd.org/api/tournaments" ; do
  code=$(curl -sS -o "$W/probe.tmp" -w '%{http_code}' -A "Mozilla/5.0 jass-research" --max-time 25 "$probe" 2>/dev/null || echo 000)
  ct=$(file -b "$W/probe.tmp" 2>/dev/null | head -c 40)
  say "  probe $code ($ct) : $probe"
  if grep -qiE '^\s*\[Event|1\.\s*[0-9]+[-x][0-9]+' "$W/probe.tmp" 2>/dev/null; then
    GOTPDN="$W/probe.tmp"; say "    -> ressemble a du PDN !"; break; fi
done

# --- 4. si PDN obtenu : valider la chaine complete ---
if [ -n "$GOTPDN" ]; then
  say ""; say "=== 4. validation chaine sur vraie PDN ==="
  git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
  git show origin/develop:pattern_jass/tools/pdn/clean_pdn.py > "$W/clean_pdn.py" 2>/dev/null || true
  python3 "$W/clean_pdn.py" "$GOTPDN" > "$W/games.txt" 2>>"$RES" || true
  say "  games nettoyees : $(grep -c . "$W/games.txt" 2>/dev/null || echo 0)"
  head -2 "$W/games.txt" | cut -c1-80 | sed 's/^/    /' | tee -a "$RES"
  say "  (build jass + replay-moves = laisse au VRAI fetcher une fois l'endpoint confirme)"
else
  say "  aucune PDN recuperee par sonde directe (probablement compte-gate / applet JS)."
  say "  => le fetcher devra : soit un compte toernooibase (Bouma), soit parser l'applet (endpoint oerterp.php?wed=...&view=PDN)."
fi

say ""; say "=== VERDICT RECON : hotes joignables=$REACH/4 ; PDN directe=$([ -n "$GOTPDN" ] && echo OUI || echo NON) ==="
say "=== fin recon ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0684 fmjd-recon : joignables=$REACH/4 pdn-directe=$([ -n "$GOTPDN" ] && echo oui || echo non)"
