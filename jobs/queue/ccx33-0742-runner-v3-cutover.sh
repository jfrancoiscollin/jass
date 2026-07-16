#!/usr/bin/env bash
# id: ccx33-0742-runner-v3-cutover
# description: final ccx33 cutover from legacy timer to runner-v3 after green R2 smoke
# expected_duration: <5 min
set -euo pipefail

EXPECTED_HOST="ubuntu-16gb-hel1-2"
[ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "wrong host" >&2; exit 2; }

CODE_DIR="/srv/jass/code"
CONTROL_DIR="/srv/jass/control"
OUT="/root/jass/jobs/results/ccx33-0742-runner-v3-cutover/artefacts"
mkdir -p "$OUT"

for path in \
  "$CODE_DIR/infra/jass-runner-v3.service" \
  "$CODE_DIR/infra/jass-runner-v3.timer" \
  "$CODE_DIR/infra/runner_v3.py" \
  /etc/jass-runner/runner-v3.env \
  /etc/jass-runner/secrets.env; do
  [ -s "$path" ] || { echo "missing prerequisite: $path" >&2; exit 3; }
done

set -a
. /etc/jass-runner/runner-v3.env
. /etc/jass-runner/secrets.env
set +a
/usr/bin/rclone lsf "$JASS_OBJSTORE_REMOTE" --max-depth 1 >/dev/null

git -C "$CONTROL_DIR" fetch origin main
git -C "$CONTROL_DIR" reset --hard origin/main
[ -s "$CONTROL_DIR/queue/pending/ccx33-0743-v3-cutover-proof.sh" ]

install -m 0644 "$CODE_DIR/infra/jass-runner-v3.service" /etc/systemd/system/jass-runner-v3.service
install -m 0644 "$CODE_DIR/infra/jass-runner-v3.timer" /etc/systemd/system/jass-runner-v3.timer
systemctl daemon-reload

UNIT="jass-runner-v3-ccx33-final-cutover-$(date +%s)"
systemd-run \
  --unit="$UNIT" \
  --on-active=2min \
  --collect \
  /bin/bash -lc '
    set -euo pipefail
    test "$(hostname)" = "ubuntu-16gb-hel1-2"
    systemctl disable --now jass-runner.timer
    systemctl enable --now jass-runner-v3.timer
    systemctl start jass-runner-v3.service
    install -d -m 0755 /var/lib/jass-runner
    {
      echo "cutover_at=$(date -Is)"
      echo "host=$(hostname)"
      echo "legacy_enabled=$(systemctl is-enabled jass-runner.timer || true)"
      echo "legacy_active=$(systemctl is-active jass-runner.timer || true)"
      echo "v3_enabled=$(systemctl is-enabled jass-runner-v3.timer || true)"
      echo "v3_active=$(systemctl is-active jass-runner-v3.timer || true)"
    } > /var/lib/jass-runner/ccx33-cutover-status.txt
  '

{
  echo "state=cutover_scheduled"
  echo "unit=$UNIT"
  echo "delay=2min"
  echo "proof_job=ccx33-0743-v3-cutover-proof"
} > "$OUT/cutover-summary.txt"
cat "$OUT/cutover-summary.txt"
