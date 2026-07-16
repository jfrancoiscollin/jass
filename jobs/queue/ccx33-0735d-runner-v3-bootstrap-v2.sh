#!/usr/bin/env bash
# id: ccx33-0735d-runner-v3-bootstrap-v2
# description: retry corrected ccx33 runner-v3 bootstrap using the routed smoke
# expected_duration: 10-20 min plus delayed cutover
set -euo pipefail
cd /root/jass

JOB_ID="ccx33-0735d-runner-v3-bootstrap-v2"
SOURCE="jobs/queue/ccx33-0735a-runner-v3-bootstrap.sh"
OUT="jobs/results/$JOB_ID/artefacts.src"
PATCHED="$OUT/bootstrap-v2.sh"
mkdir -p "$OUT"
test -s "$SOURCE"

python3 - "$SOURCE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src, dst = map(Path, sys.argv[1:])
text = src.read_text(encoding='utf-8')
old = 'ccx33-0735a-runner-v3-bootstrap'
new = 'ccx33-0735d-runner-v3-bootstrap-v2'
if old not in text:
    raise SystemExit('source bootstrap ID not found')
text = text.replace(old, new)
if 'SMOKE_ID="ccx33-0735c-v3-smoke"' not in text:
    raise SystemExit('correct routed smoke ID missing from source')
dst.write_text(text, encoding='utf-8')
PY
chmod 0700 "$PATCHED"
printf 'source=%s\n' "$SOURCE" > "$OUT/retry-source.txt"
printf 'source_sha256=%s\n' "$(sha256sum "$SOURCE" | awk '{print $1}')" >> "$OUT/retry-source.txt"
printf 'patched_sha256=%s\n' "$(sha256sum "$PATCHED" | awk '{print $1}')" >> "$OUT/retry-source.txt"
bash -n "$PATCHED"
bash "$PATCHED"
