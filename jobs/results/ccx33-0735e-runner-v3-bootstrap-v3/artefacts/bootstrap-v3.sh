#!/usr/bin/env bash
# id: ccx33-0735e-runner-v3-bootstrap-v3
# description: bootstrap, smoke and schedule runner-v3 cutover on ccx33
# expected_duration: 10-20 min plus delayed cutover
set -euo pipefail

JOB_ID="ccx33-0735e-runner-v3-bootstrap-v3"
ROOT="/root/jass"
OUT="$ROOT/jobs/results/$JOB_ID/artefacts.src"
HOST_SCRIPT="$OUT/bootstrap-host.sh"
EXPECTED_HOST="ubuntu-16gb-hel1-2"
mkdir -p "$OUT"

cat > "$HOST_SCRIPT" <<'HOSTSCRIPT'
#!/usr/bin/env bash
set -euo pipefail

JOB_ID="ccx33-0735e-runner-v3-bootstrap-v3"
EXPECTED_HOST="ubuntu-16gb-hel1-2"
ROOT="/root/jass"
OUT="$ROOT/jobs/results/$JOB_ID/artefacts.src"
CODE_DIR="/srv/jass/code"
CONTROL_DIR="/srv/jass/control"
CONTROL_URL="git@github-jass-control-ccx33:jfrancoiscollin/jass-control.git"
SMOKE_ID="ccx33-0735c-v3-smoke"
SMOKE_STATUS="$CONTROL_DIR/status/${SMOKE_ID}.json"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/host-bootstrap.log") 2>&1

say(){ printf '%s %s\n' "$(date -Is)" "$*"; }
die(){ say "ABORT: $*"; exit 1; }

[ "$(hostname)" = "$EXPECTED_HOST" ] || die "wrong host $(hostname), expected $EXPECTED_HOST"
[ -d "$ROOT/.git" ] || die "$ROOT is not a Git repository"
command -v git >/dev/null || die "git missing"
command -v python3 >/dev/null || die "python3 missing"
command -v systemctl >/dev/null || die "systemctl missing"

say "capturing preflight"
{
  echo "host=$(hostname)"
  echo "legacy_timer_enabled=$(systemctl is-enabled jass-runner.timer 2>/dev/null || true)"
  echo "legacy_timer_active=$(systemctl is-active jass-runner.timer 2>/dev/null || true)"
  echo "v3_timer_enabled=$(systemctl is-enabled jass-runner-v3.timer 2>/dev/null || true)"
  echo "v3_timer_active=$(systemctl is-active jass-runner-v3.timer 2>/dev/null || true)"
  echo "root_main_sha=$(git -C "$ROOT" rev-parse HEAD)"
} > "$OUT/preflight.txt"

if ! command -v rclone >/dev/null; then
  say "installing rclone from the system package repository"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y rclone
fi
RCLONE_BIN="$(command -v rclone)"
[ -x "$RCLONE_BIN" ] || die "rclone unavailable"

CODE_URL="$(git -C "$ROOT" remote get-url origin)"
[ -n "$CODE_URL" ] || die "cannot resolve Jass origin URL"
say "validating private control-repository access"
git ls-remote "$CONTROL_URL" refs/heads/main > "$OUT/control-ls-remote.txt" || die "cannot read private jass-control repository"
grep -Eq '^[0-9a-f]{40}[[:space:]]+refs/heads/main$' "$OUT/control-ls-remote.txt" || die "jass-control main ref not found"

sync_repo(){
  local dir="$1" url="$2" branch="$3"
  mkdir -p "$(dirname "$dir")"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" remote set-url origin "$url"
    git -C "$dir" fetch --prune origin "$branch"
    git -C "$dir" checkout -B "$branch" "origin/$branch"
    git -C "$dir" reset --hard "origin/$branch"
    git -C "$dir" clean -fd
  else
    rm -rf "$dir"
    git clone --single-branch --branch "$branch" "$url" "$dir"
  fi
}

say "synchronizing code and control clones"
sync_repo "$CODE_DIR" "$CODE_URL" develop
sync_repo "$CONTROL_DIR" "$CONTROL_URL" main

git -C "$CONTROL_DIR" config user.name "Jass Runner $EXPECTED_HOST"
git -C "$CONTROL_DIR" config user.email "jass-runner-ccx33@localhost"
git -C "$CONTROL_DIR" push --dry-run origin HEAD:main > "$OUT/control-push-dry-run.txt" 2>&1 || die "jass-control is not writable from ccx33"

install -d -m 0755 /srv/jass /var/lib/jass-runner
install -d -m 0700 /etc/jass-runner
ENV_TMP="$OUT/runner-v3.env"
cat > "$ENV_TMP" <<EOF
JASS_CODE_REPO_DIR=/srv/jass/code
JASS_CODE_REMOTE=origin
JASS_CODE_REF=develop
JASS_CONTROL_REPO_DIR=/srv/jass/control
JASS_CONTROL_REMOTE=origin
JASS_CONTROL_REF=main
JASS_CONTROL_LAYOUT=v3
JASS_SPOOL_ROOT=/var/lib/jass-runner
JASS_KEEP_LOCAL_RESULTS=0
JASS_RESULT_BACKEND=rclone
JASS_OBJSTORE_REMOTE=r2:jass-data
JASS_OBJSTORE_PREFIX=runs
RCLONE_BIN=$RCLONE_BIN
JASS_UPLOAD_RETRIES=3
JASS_GIT_RETRIES=5
JASS_MAX_LOG_BYTES=1000000
JASS_HOST_FILTER=ccx33-
JASS_ALLOW_LEGACY_JOB_PATHS=0
EOF
install -m 0644 "$ENV_TMP" /etc/jass-runner/runner-v3.env

if [ -f /etc/jass-runner/secrets.env ] && grep -q 'replace-me' /etc/jass-runner/secrets.env; then
  die "/etc/jass-runner/secrets.env still contains placeholders"
fi
{
  echo "secrets_env_present=$([ -s /etc/jass-runner/secrets.env ] && echo yes || echo no)"
  echo "rclone_config_present=$([ -s /root/.config/rclone/rclone.conf ] && echo yes || echo no)"
} > "$OUT/credential-sources.txt"

set -a
. /etc/jass-runner/runner-v3.env
if [ -s /etc/jass-runner/secrets.env ]; then . /etc/jass-runner/secrets.env; fi
set +a
say "validating R2 connectivity without exposing credentials"
"$RCLONE_BIN" lsf "$JASS_OBJSTORE_REMOTE" --max-depth 1 > "$OUT/r2-root-listing.txt" || die "R2 connectivity failed; credentials/configuration missing or invalid"

say "installing dormant runner-v3 units"
install -m 0644 "$CODE_DIR/infra/jass-runner-v3.service" /etc/systemd/system/jass-runner-v3.service
install -m 0644 "$CODE_DIR/infra/jass-runner-v3.timer" /etc/systemd/system/jass-runner-v3.timer
systemctl daemon-reload
systemctl disable --now jass-runner-v3.timer >/dev/null 2>&1 || true

for path in \
  "$CODE_DIR/infra/runner_v3.py" \
  "$CONTROL_DIR/queue/pending/${SMOKE_ID}.sh" \
  /etc/systemd/system/jass-runner-v3.service \
  /etc/systemd/system/jass-runner-v3.timer \
  /etc/jass-runner/runner-v3.env; do
  [ -e "$path" ] || die "missing prerequisite $path"
done

say "starting manual runner-v3 ticks for smoke"
SMOKE_STATE=""
for attempt in $(seq 1 24); do
  systemctl reset-failed jass-runner-v3.service >/dev/null 2>&1 || true
  if ! systemctl start jass-runner-v3.service; then
    journalctl -u jass-runner-v3.service -n 100 --no-pager > "$OUT/v3-service-error.log" 2>&1 || true
    die "manual runner-v3 tick failed"
  fi
  git -C "$CONTROL_DIR" fetch origin main
  git -C "$CONTROL_DIR" reset --hard origin/main
  if [ -s "$SMOKE_STATUS" ]; then
    SMOKE_STATE="$(python3 - "$SMOKE_STATUS" <<'PY'
import json,sys
try:
    print(json.load(open(sys.argv[1])).get('state',''))
except Exception:
    print('')
PY
)"
    say "smoke state=$SMOKE_STATE"
    case "$SMOKE_STATE" in
      completed) break ;;
      failed|upload_failed) die "runner-v3 smoke ended in $SMOKE_STATE" ;;
    esac
  fi
  sleep 30
done
[ "$SMOKE_STATE" = completed ] || die "runner-v3 smoke did not complete within the timeout"

python3 - "$SMOKE_STATUS" "$EXPECTED_HOST" <<'PY'
import json,sys
p,expected_host=sys.argv[1:]
data=json.load(open(p))
assert data.get('state') == 'completed', data
assert data.get('exit_code') == 0, data
assert data.get('host') == expected_host, data
assert data.get('code_ref') == 'develop', data
assert str(data.get('result_uri','')).startswith('r2:jass-data/runs/'), data
print(json.dumps(data, indent=2, sort_keys=True))
PY
cp "$SMOKE_STATUS" "$OUT/smoke-status.json"

say "scheduling delayed ccx33 cutover"
CUTOVER_UNIT="jass-runner-v3-ccx33-cutover-$(date +%s)"
systemd-run \
  --unit="$CUTOVER_UNIT" \
  --on-active=8min \
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
  echo "state=bootstrap_completed"
  echo "host=$(hostname)"
  echo "code_sha=$(git -C "$CODE_DIR" rev-parse HEAD)"
  echo "control_sha=$(git -C "$CONTROL_DIR" rev-parse HEAD)"
  echo "smoke_state=$SMOKE_STATE"
  echo "cutover_unit=$CUTOVER_UNIT"
  echo "cutover_delay=8min"
  echo "legacy_timer_left_running_for_reap=true"
} > "$OUT/bootstrap-summary.txt"
systemctl list-timers --all "${CUTOVER_UNIT}.timer" --no-pager > "$OUT/cutover-timer.txt" || true
cat "$OUT/bootstrap-summary.txt"
HOSTSCRIPT
chmod 0700 "$HOST_SCRIPT"

[ "$(hostname)" = "$EXPECTED_HOST" ] || {
  echo "wrong legacy host: $(hostname), expected $EXPECTED_HOST" >&2
  exit 2
}

UNIT="jass-runner-v3-ccx33-bootstrap-$(date +%s)"
echo "starting host bootstrap as transient unit: $UNIT"
systemd-run --unit="$UNIT" --wait --collect /bin/bash "$HOST_SCRIPT"
cat "$OUT/bootstrap-summary.txt"
