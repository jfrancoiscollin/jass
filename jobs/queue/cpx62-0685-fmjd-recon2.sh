#!/usr/bin/env bash
# id: cpx62-0685-fmjd-recon2
# description: RECON-2 toernooibase — la box joint le site (0684). Cible l'endpoint REEL des parties : la frame de requete
# /opvraag/keuze1nieuw.php + l'applet oerterp.php?wed=<id>&view=N. Sonde les view= pour trouver celle qui renvoie du PDN
# (lignes "1. 32-28" / "[Event"). Tranche : A faisable SANS compte (vue PDN trouvee -> je construis le fetcher) ou compte-gate
# (repli Bouma C). Leger, curl-only, aucun scraping massif. Sauve les pages en artefacts pour lecture structure.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0685-fmjd-recon2/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0685-fmjd-recon2/artefacts"
W=/root/cw-fmjdr2; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
UA="Mozilla/5.0 jass-research"; BASE="https://toernooibase.kndb.nl"
START=$(date +%s)
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
fetch(){ curl -sS -A "$UA" --max-time 25 "$1"; }

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
say "=== RECON-2 toernooibase endpoints — $(date -u +%FT%TZ) ==="

# --- A. frame de requete + pages opvraag ---
say ""; say "=== A. /opvraag/keuze1nieuw.php + liens ==="
fetch "$BASE/opvraag/keuze1nieuw.php" > "$W/keuze1.html" 2>/dev/null || true
say "  keuze1nieuw.php : $(stat -c%s "$W/keuze1.html" 2>/dev/null||echo 0)o"
grep -ioE "href=['\"][^'\"]*\.php[^'\"]*['\"]|action=['\"][^'\"]*['\"]|wed=[0-9]+|view=[0-9]+" "$W/keuze1.html" 2>/dev/null | sort -u | head -30 | sed 's/^/    /' | tee -a "$RES"
cp "$W/keuze1.html" "$ART/keuze1.html" 2>/dev/null || true

# --- B. applet oerterp.php : sonder les view= sur un id de partie connu ---
say ""; say "=== B. oerterp.php?wed=529323 view=0..9 (cherche PDN) ==="
APBASE="$BASE/applet/oerterpapplet2.0/oerterp.php?kl=23&Id=606&r=16&jr=0&wed=529323"
FOUND=""
for v in 0 1 2 3 4 5 6 7 8 9 pdn PDN; do
  fetch "$APBASE&view=$v" > "$W/v_$v.html" 2>/dev/null || true
  sz=$(stat -c%s "$W/v_$v.html" 2>/dev/null||echo 0)
  ispdn=$(grep -cE '^\s*\[Event|[0-9]+\.\s*[0-9]{1,2}[-x][0-9]{1,2}|[0-9]{1,2}[-x][0-9]{1,2}\s+[0-9]{1,2}[-x][0-9]{1,2}' "$W/v_$v.html" 2>/dev/null || echo 0)
  say "  view=$v : ${sz}o  pdn-lines=$ispdn"
  if [ "${ispdn:-0}" -gt 2 ] && [ -z "$FOUND" ]; then FOUND="$v"; cp "$W/v_$v.html" "$ART/oerterp_view_$v.txt"; fi
done

# --- C. autres endpoints d'export plausibles ---
say ""; say "=== C. endpoints export plausibles ==="
for u in \
  "$BASE/opvraag/pdn.php?wed=529323" \
  "$BASE/pdn.php?wed=529323" \
  "$BASE/applet/oerterpapplet2.0/pdn.php?wed=529323" \
  "$BASE/opvraag/partij.php?wed=529323" ; do
  code=$(curl -sS -o "$W/exp.tmp" -w '%{http_code}' -A "$UA" --max-time 20 "$u" 2>/dev/null||echo 000)
  ispdn=$(grep -cE '^\s*\[Event|[0-9]+\.\s*[0-9]{1,2}[-x][0-9]{1,2}' "$W/exp.tmp" 2>/dev/null||echo 0)
  say "  $code pdn-lines=$ispdn : $u"
  [ "${ispdn:-0}" -gt 2 ] && [ -z "$FOUND" ] && { FOUND="export:$u"; cp "$W/exp.tmp" "$ART/export_hit.txt"; }
done

say ""
if [ -n "$FOUND" ]; then
  say "=== VERDICT : PDN ACCESSIBLE sans compte via '$FOUND' => FETCHER FAISABLE (je le construis) ==="
else
  say "=== VERDICT : PDN pas trouvee en direct (applet JS / compte-gate) => cracker l'applet coûteux ; REPLI Bouma (C) recommandé ==="
fi
say "  (pages sauvees en artefacts pour lecture structure)"
say "=== fin recon2 ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0685 fmjd-recon2 : PDN-endpoint=$([ -n "$FOUND" ] && echo "$FOUND" || echo none)"
