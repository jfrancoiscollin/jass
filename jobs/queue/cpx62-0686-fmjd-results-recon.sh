#!/usr/bin/env bash
# id: cpx62-0686-fmjd-results-recon
# description: RECON-3 results.fmjd.org (DraughtArbiter Pro) — creuser l'avenue FMJD officielle (toernooibase = login-gate, 0685).
# Suit le 302, cartographie la structure (tournois -> rondes -> parties), cherche un export/telechargement PDN OUVERT. Si trouve
# -> A faisable via FMJD officiel (je construis le fetcher). Sinon -> confirme repli Bouma (C). Curl-only, leger, artefacts sauves.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0686-fmjd-results-recon/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0686-fmjd-results-recon/artefacts"
W=/root/cw-fmjdr3; rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
UA="Mozilla/5.0 jass-research"
START=$(date +%s)
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
gf(){ curl -sSL -A "$UA" --max-time 30 "$1"; }   # -L suit les redirections

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
say "=== RECON-3 results.fmjd.org (DraughtArbiter) — $(date -u +%FT%TZ) ==="

# --- A. landing (suivre redirections) ---
say ""; say "=== A. results.fmjd.org (suivi 302) ==="
curl -sSL -A "$UA" --max-time 30 -D "$W/hdr.txt" "https://results.fmjd.org/" > "$W/landing.html" 2>/dev/null || true
FINAL=$(grep -iE '^location:' "$W/hdr.txt" 2>/dev/null | tail -1 | tr -d '\r' | awk '{print $2}')
say "  redirections -> ${FINAL:-(aucune / direct)}  ; landing $(stat -c%s "$W/landing.html" 2>/dev/null||echo 0)o"
cp "$W/landing.html" "$ART/landing.html" 2>/dev/null || true
say "  liens (php/html/asp/tournament/game/pdn) :"
grep -ioE "href=['\"][^'\"]*['\"]" "$W/landing.html" 2>/dev/null | grep -iE 'pdn|download|export|tourn|game|partij|result|\.php|\.html|id=' | sort -u | head -30 | sed 's/^/    /' | tee -a "$RES"

# --- B. suivre le 1er lien tournoi + chercher parties/PDN ---
say ""; say "=== B. 1er lien tournoi -> parties/PDN ==="
T1=$(grep -ioE "href=['\"][^'\"]*['\"]" "$W/landing.html" 2>/dev/null | grep -iE 'tourn|id=|result' | head -1 | sed -E "s/href=['\"]//; s/['\"]$//")
if [ -n "$T1" ]; then
  case "$T1" in http*) TU="$T1";; /*) TU="https://results.fmjd.org$T1";; *) TU="https://results.fmjd.org/$T1";; esac
  say "  tournoi: $TU"
  gf "$TU" > "$W/t1.html" 2>/dev/null || true
  cp "$W/t1.html" "$ART/tournament1.html" 2>/dev/null || true
  say "  liens PDN/game dans le tournoi :"
  grep -ioE "href=['\"][^'\"]*['\"]" "$W/t1.html" 2>/dev/null | grep -iE 'pdn|game|partij|download|export|round|ronde' | sort -u | head -25 | sed 's/^/    /' | tee -a "$RES"
else
  say "  (aucun lien tournoi repéré dans la landing)"
fi

# --- C. endpoints PDN plausibles DraughtArbiter ---
say ""; say "=== C. endpoints PDN plausibles ==="
FOUND=""
for u in \
  "https://results.fmjd.org/games.pdn" \
  "https://results.fmjd.org/pdn/" \
  "https://dra.fmjd.org/" ; do
  code=$(curl -sSL -o "$W/c.tmp" -w '%{http_code}' -A "$UA" --max-time 25 "$u" 2>/dev/null||echo 000)
  ispdn=$(grep -cE '^\s*\[Event|[0-9]+\.\s*[0-9]{1,2}[-x][0-9]{1,2}' "$W/c.tmp" 2>/dev/null||echo 0)
  say "  $code pdn-lines=$ispdn : $u"
  [ "${ispdn:-0}" -gt 2 ] && [ -z "$FOUND" ] && { FOUND="$u"; cp "$W/c.tmp" "$ART/pdn_hit.txt"; }
done

# grep global : une balise <a> .pdn n'importe ou dans les pages recuperees
PDNLINK=$(grep -rhoiE "href=['\"][^'\"]*\.pdn['\"]" "$W"/*.html 2>/dev/null | head -1)
[ -n "$PDNLINK" ] && say "  LIEN .pdn direct repéré : $PDNLINK"

say ""
if [ -n "$FOUND" ] || [ -n "$PDNLINK" ]; then
  say "=== VERDICT : PDN OUVERT sur FMJD officiel (${FOUND:-$PDNLINK}) => FETCHER FAISABLE ==="
else
  say "=== VERDICT : pas de PDN ouvert repéré ici non plus => repli Bouma (C) confirmé. (lire artefacts pour structure fine) ==="
fi
say "=== fin recon3 ($(( $(date +%s)-START ))s) ==="
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0686 fmjd-results-recon : pdn-ouvert=$([ -n "$FOUND$PDNLINK" ] && echo oui || echo non)"
