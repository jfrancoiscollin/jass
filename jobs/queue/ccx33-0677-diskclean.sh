#!/usr/bin/env bash
# id: ccx33-0677-diskclean
# description: MAINTENANCE disque (demande JFC apres ccx33 rempli a 100% => runner mort + 0670 boucle). Nettoie les scratch de
# jobs STALE (/root/cw-* non modifies depuis >2h => JAMAIS le dossier d'un job actif, protege par le mtime) + .compile-tmp.
# GARDE egdb_*, jass, jass-scan, jass-geom*. Rapporte df avant/apres. Rapide, sur, aucun NNUE. A re-queuer au besoin ;
# l'auto-clean permanent est desormais en tete de chaque job (check-list CLAUDE.md).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0677-diskclean/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0677-diskclean/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== DISKCLEAN ccx33 — $(hostname) $(date -u +%FT%TZ) ==="
say "  AVANT : $(df -Ph /root | awk 'NR==2{print "used="$3" avail="$4" ("$5")"}')"
say "  gros /root/* (top 12) :"; du -xsh /root/* 2>/dev/null | sort -h | tail -12 | sed 's/^/    /' | tee -a "$RES"

# --- nettoyage SUR : cw-* stale (>120 min => pas le job actif) + .compile-tmp ---
CW_STALE=$(find /root -maxdepth 1 -name 'cw-*' -type d -mmin +120 2>/dev/null | wc -l)
say "  cw-* stale (>2h, supprimés) : $CW_STALE"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +120 -exec rm -rf {} + 2>/dev/null || true
rm -rf /root/.compile-tmp/* 2>/dev/null || true
# vieilles branches de build (sparring/sacbranch) si stale >6h
find /root -maxdepth 1 \( -name 'jass-sacbranch-*' -o -name 'jass-sparring*' \) -mmin +360 -exec rm -rf {} + 2>/dev/null || true

say "  APRÈS : $(df -Ph /root | awk 'NR==2{print "used="$3" avail="$4" ("$5")"}')"
AVAIL_MB=$(df -Pm /root | awk 'NR==2{print $4}')
say "  => $AVAIL_MB Mo libres."
[ "${AVAIL_MB:-0}" -gt 5000 ] 2>/dev/null && say "  ✓ disque sain" || say "  ⚠ ENCORE JUSTE (<5Go) — investiguer egdb/jass"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0677 diskclean ccx33 : ${AVAIL_MB}Mo libres" && say "  RESULTS committé ✓" || say "  ⚠ commit"
say "=== fin diskclean ==="
