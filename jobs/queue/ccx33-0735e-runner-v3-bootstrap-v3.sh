#!/usr/bin/env bash
# id: ccx33-0735e-runner-v3-bootstrap-v3
# description: retry ccx33 runner-v3 bootstrap with dedicated jass-control SSH alias
# expected_duration: 10-20 min plus delayed cutover
set -euo pipefail
cd /root/jass

JOB_ID="ccx33-0735e-runner-v3-bootstrap-v3"
SOURCE="jobs/queue/ccx33-0735a-runner-v3-bootstrap.sh"
OUT="jobs/results/$JOB_ID/artefacts.src"
PATCHED="$OUT/bootstrap-v3.sh"
mkdir -p "$OUT"
test -s "$SOURCE"

test -s /root/.ssh/jass-control-ccx33
test -s /root/.ssh/config
grep -q '^Host github-jass-control-ccx33$' /root/.ssh/config

git ls-remote \
  git@github-jass-control-ccx33:jfrancoiscollin/jass-control.git \
  refs/heads/main > "$OUT/control-access.txt"
grep -Eq '^[0-9a-f]{40}[[:space:]]+refs/heads/main$' "$OUT/control-access.txt"

python3 - "$SOURCE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src, dst = map(Path, sys.argv[1:])
text = src.read_text(encoding='utf-8')
replacements = {
    'ccx33-0735a-runner-v3-bootstrap': 'ccx33-0735e-runner-v3-bootstrap-v3',
    'git@github.com:jfrancoiscollin/jass-control.git': 'git@github-jass-control-ccx33:jfrancoiscollin/jass-control.git',
    'SMOKE_ID="ccx33-0735b-v3-smoke"': 'SMOKE_ID="ccx33-0735c-v3-smoke"',
}
for old, new in replacements.items():
    text = text.replace(old, new)
if 'CONTROL_URL="git@github-jass-control-ccx33:jfrancoiscollin/jass-control.git"' not in text:
    raise SystemExit('dedicated control URL patch missing')
if 'SMOKE_ID="ccx33-0735c-v3-smoke"' not in text:
    raise SystemExit('routed smoke ID missing')
dst.write_text(text, encoding='utf-8')
PY

chmod 0700 "$PATCHED"
bash -n "$PATCHED"
sha256sum "$SOURCE" "$PATCHED" > "$OUT/source-checksums.txt"
bash "$PATCHED"
