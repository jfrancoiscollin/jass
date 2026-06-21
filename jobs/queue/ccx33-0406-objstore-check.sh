#!/usr/bin/env bash
# id: ccx33-0406-objstore-check
# description: PROBE LEGER (aucun transfert) - verifie si les variables d'env object-store (R2) sont bien arrivees
# jusqu'au job du runner, puis teste la connectivite rclone. Diagnostic avant tout sync. Si DORMANT -> le runner
# n'a pas (encore) les variables (propagation via nouvelle session/restart a regler). Si connecte -> on lance le sync.
set -uo pipefail
cd /root/jass
echo "=== variables d'env object-store visibles dans le job ? (presence seulement, pas de valeurs) ==="
echo "JASS_OBJSTORE_REMOTE present : $([ -n "${JASS_OBJSTORE_REMOTE:-}" ] && echo OUI || echo NON)"
echo "JASS_OBJSTORE_PREFIX present : $([ -n "${JASS_OBJSTORE_PREFIX:-}" ] && echo OUI || echo NON)"
echo "RCLONE_CONFIG_* count        : $(env | grep -c '^RCLONE_CONFIG_' || true)"
echo "RCLONE_CONFIG_R2_SECRET set  : $([ -n "${RCLONE_CONFIG_R2_SECRET_ACCESS_KEY:-}" ] && echo OUI || echo NON)"
echo
echo "=== objstore.sh check (config + bootstrap rclone + connectivite) ==="
tools/objstore.sh check || true
echo
echo "=== egress test (R2 endpoint + rclone download) ==="
echo -n "downloads.rclone.org joignable : "; curl -fsSI --max-time 15 https://downloads.rclone.org/version.txt >/dev/null 2>&1 && echo OUI || echo "NON (egress bloque ?)"
EP="${RCLONE_CONFIG_R2_ENDPOINT:-}"
if [ -n "$EP" ]; then echo -n "endpoint R2 joignable : "; curl -fsSI --max-time 15 "$EP" >/dev/null 2>&1 && echo OUI || echo "NON/refuse (normal si auth requise, mais doit repondre)"; fi
echo "=== fin probe ==="
