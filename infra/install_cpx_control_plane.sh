#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${JASS_CODE_DIR:-/srv/jass/code}"
TOKEN_DIR=/etc/jass-control-plane
STATE_DIR=/var/lib/jass-control-plane
UNIT=/etc/systemd/system/jass-control-plane.service

install -d -m 0700 "$TOKEN_DIR"
install -d -m 0700 "$STATE_DIR"

if [[ ! -s "$TOKEN_DIR/token" ]]; then
  umask 077
  python3 - <<'PY' > "$TOKEN_DIR/token"
import secrets
print(secrets.token_urlsafe(48))
PY
  chmod 0600 "$TOKEN_DIR/token"
fi

install -m 0644 "$ROOT/infra/jass-control-plane.service" "$UNIT"
python3 -m py_compile "$ROOT/infra/cpx_control_plane.py"
python3 -m unittest "$ROOT/infra/tests/test_cpx_control_plane.py"
systemctl daemon-reload
systemctl enable --now jass-control-plane.service
sleep 1
curl --fail --silent --show-error http://127.0.0.1:8765/health
printf '\ncontrol-plane installed; token remains local at %s\n' "$TOKEN_DIR/token"
