#!/usr/bin/env bash
# Diagnostique puis relance le runner v3 sur HOME (WSL2, hostname `User`).
#
# À LANCER SUR LA MACHINE HOME ELLE-MÊME, dans la fenêtre Ubuntu (WSL) :
#
#     sudo bash /srv/jass/code/infra/home-runner-restart.sh
#
# ou, si le clone est absent/périmé :
#
#     curl -sSL https://raw.githubusercontent.com/jfrancoiscollin/jass/develop/infra/home-runner-restart.sh | sudo bash
#
# Le runner HOME est mort le 2026-07-31 vers 06:32 UTC. Les leviers GitOps sont
# déjà corrects côté dépôt de contrôle (`state/host-active/User` existe, donc la
# pause globale ne s'applique pas à HOME) : ce qui manque est LOCAL à la machine.
# C'est pourquoi ce script doit tourner là-bas et nulle part ailleurs.
#
# Il commence par un DIAGNOSTIC en lecture seule, puis n'agit que sur ce qui est
# réparable sans décision : daemon-reload, enable + start du timer, un tick
# manuel. Il ne touche NI aux credentials, NI au dépôt de contrôle, NI à la file.
set -uo pipefail

HOSTNAME_ATTENDU="User"
CODE=/srv/jass/code
CTRL=/srv/jass/control
ENVD=/etc/jass-runner
UNIT=jass-runner-v3
LEGACY=jass-runner

ko=0
ok()   { printf '  [ok]   %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
bad()  { printf '  [KO]   %s\n' "$*"; ko=$((ko + 1)); }
titre(){ printf '\n=== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Ce script doit tourner en root (sudo)."; exit 1; }

titre "1. Identité de la machine"
H="$(hostname)"
echo "  hostname = $H"
echo "  uptime   = $(uptime -p 2>/dev/null || true)"
if [ "$H" = "$HOSTNAME_ATTENDU" ]; then
  ok "c'est bien HOME"
else
  warn "hostname inattendu (attendu '$HOSTNAME_ATTENDU'). Si cette machine a été"
  warn "renommée, l'exemption de pause 'state/host-active/$HOSTNAME_ATTENDU' du"
  warn "dépôt de contrôle ne la couvre PLUS : le runner verra la pause globale et"
  warn "ne réclamera rien. Il faudra committer 'state/host-active/$H'."
fi

titre "2. systemd disponible dans WSL"
if systemctl is-system-running >/dev/null 2>&1 || \
   [ "$(systemctl is-system-running 2>/dev/null || true)" = degraded ]; then
  ok "systemd actif ($(systemctl is-system-running 2>/dev/null || echo '?'))"
else
  bad "systemd inactif — c'est la panne la plus probable après un redémarrage de"
  bad "Windows. Corriger puis relancer ce script :"
  bad "    printf '[boot]\\nsystemd=true\\n' | sudo tee /etc/wsl.conf"
  bad "    puis depuis PowerShell : wsl --shutdown, et rouvrir Ubuntu."
  exit 2
fi

titre "3. Clones et configuration locale"
for d in "$CODE" "$CTRL"; do
  if [ -d "$d/.git" ]; then ok "$d présent"; else bad "$d ABSENT"; fi
done
for f in "$ENVD/runner-v3.env" "$ENVD/secrets.env"; do
  if [ -s "$f" ]; then ok "$f présent"; else bad "$f ABSENT ou vide"; fi
done
if [ -f "$ENVD/runner-v3.env" ]; then
  FILT="$(grep -E '^JASS_HOST_FILTER=' "$ENVD/runner-v3.env" 2>/dev/null | tail -1 || true)"
  echo "  ${FILT:-JASS_HOST_FILTER absent du fichier (défaut = tout réclamer)}"
  case "$FILT" in
    *home-*) ok "portée 'home-' — ne volera pas les jobs cpx62/ccx33" ;;
    "")      bad "portée ABSENTE : ce runner réclamerait AUSSI les jobs cpx62." ;;
    *)       warn "portée = $FILT (vérifier qu'elle vaut bien 'home-')" ;;
  esac
fi
[ "$ko" -eq 0 ] || { echo; echo "Diagnostic KO ($ko point(s)) — rien n'a été démarré."; exit 3; }

titre "4. État actuel des unités"
systemctl list-unit-files "${UNIT}.*" "${LEGACY}.*" --no-pager 2>/dev/null || true
echo "  --- dernier tick v3 :"
journalctl -u "${UNIT}.service" -n 15 --no-pager 2>/dev/null || echo "  (aucun journal)"

titre "5. Accès réseau (git + stockage objet)"
if git -C "$CODE" ls-remote --exit-code origin develop >/dev/null 2>&1; then
  ok "git: origin/develop joignable (clé de déploiement OK)"
else
  bad "git: origin/develop INJOIGNABLE — clé de déploiement ou réseau."
fi
if git -C "$CTRL" ls-remote --exit-code origin main >/dev/null 2>&1; then
  ok "git: jass-control/main joignable"
else
  bad "git: jass-control/main INJOIGNABLE — le runner ne peut pas réclamer de job."
fi
if command -v rclone >/dev/null 2>&1; then
  set -a; . "$ENVD/runner-v3.env"; . "$ENVD/secrets.env"; set +a
  if rclone lsd "${JASS_OBJSTORE_REMOTE%%/*}" >/dev/null 2>&1; then
    ok "rclone: stockage objet joignable"
  else
    warn "rclone: stockage objet injoignable — les jobs tourneront mais la"
    warn "publication finira en 'upload_failed' (rejouée au tick suivant)."
  fi
else
  warn "rclone absent — publication impossible."
fi
[ "$ko" -eq 0 ] || { echo; echo "Diagnostic KO ($ko point(s)) — rien n'a été démarré."; exit 4; }

titre "6. Relance"
systemctl daemon-reload
systemctl enable --now "${UNIT}.timer"
# La bascule v3 est faite : l'ancien timer ne doit plus tourner en parallèle.
if systemctl is-enabled "${LEGACY}.timer" >/dev/null 2>&1; then
  systemctl disable --now "${LEGACY}.timer" || true
  ok "ancien timer v2 désactivé"
fi
systemctl start "${UNIT}.service" || true
echo "  --- tick manuel :"
journalctl -u "${UNIT}.service" -n 40 --no-pager 2>/dev/null || true

titre "7. Vérification"
systemctl list-timers "${UNIT}.timer" --no-pager 2>/dev/null || true
cat <<EOF

Le timer tique toutes les 5 min. Pour confirmer que HOME est de nouveau dans la
flotte, surveiller côté dépôt de contrôle l'apparition d'un commit signé
'Jass Runner User' :

    git -C $CTRL fetch origin main && git -C $CTRL log origin/main --oneline -5

Un job 'home-*' déposé dans queue/pending/ doit passer en running dans les 5 min.
Rappel : ce runner ne tourne QUE quand le PC est allumé et WSL démarré. Garder
une fenêtre Ubuntu ouverte, ou lancer 'wsl' au démarrage de Windows.
EOF
