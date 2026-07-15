#!/usr/bin/env bash
# id: cpx62-0730-runner-v3-cutover
# description: validate runner-v3 smoke then atomically switch systemd timers
# expected_duration: <1 min plus delayed cutover
set -euo pipefail

JOB_ID="cpx62-0730-runner-v3-cutover"
OUT="/root/jass/jobs/results/${JOB_ID}/artefacts.src"
mkdir -p "$OUT"

for path in \
  /etc/systemd/system/jass-runner-v3.service \
  /etc/systemd/system/jass-runner-v3.timer \
  /etc/jass-runner/runner-v3.env \
  /etc/jass-runner/secrets.env \
  /srv/jass/code/infra/runner_v3.py \
  /srv/jass/control/status/smoke-develop-object-store.json; do
  test -e "$path" || { echo "missing prerequisite: $path" >&2; exit 1; }
done

python3 - <<'PY'
import json
from pathlib import Path
p = Path('/srv/jass/control/status/smoke-develop-object-store.json')
data = json.loads(p.read_text())
assert data.get('state') == 'completed', data
assert data.get('exit_code') == 0, data
assert data.get('code_ref') == 'develop', data
assert str(data.get('result_uri', '')).startswith('r2:jass-data/runs/'), data
print('validated smoke:', data['attempt_id'], data['code_sha'])
PY

git -C /srv/jass/code fetch origin develop
git -C /srv/jass/code reset --hard origin/develop

test "$(git -C /srv/jass/code branch --show-current)" = "develop"

{
  echo "scheduled_at=$(date -Is)"
  echo "host=$(hostname)"
  echo "code_sha=$(git -C /srv/jass/code rev-parse HEAD)"
  echo "legacy_timer_enabled=$(systemctl is-enabled jass-runner.timer || true)"
  echo "v3_timer_enabled=$(systemctl is-enabled jass-runner-v3.timer || true)"
  echo "cutover_delay=8min"
} > "$OUT/cutover-plan.txt"

# Run outside this service's ProtectSystem namespace. The eight-minute delay
# leaves the legacy timer one full tick to reap and archive this final job.
UNIT="jass-runner-v3-cutover-$(date +%s)"
systemd-run \
  --unit="$UNIT" \
  --on-active=8min \
  --collect \
  /bin/bash -lc '
    set -euo pipefail
    systemctl disable --now jass-runner.timer
    systemctl enable --now jass-runner-v3.timer
    systemctl start jass-runner-v3.service
    {
      echo "cutover_at=$(date -Is)"
      echo "legacy_enabled=$(systemctl is-enabled jass-runner.timer || true)"
      echo "legacy_active=$(systemctl is-active jass-runner.timer || true)"
      echo "v3_enabled=$(systemctl is-enabled jass-runner-v3.timer || true)"
      echo "v3_active=$(systemctl is-active jass-runner-v3.timer || true)"
    } > /var/lib/jass-runner/cutover-status.txt
  '

echo "scheduled transient cutover unit: $UNIT"
systemctl list-timers --all "${UNIT}.timer" --no-pager || true
