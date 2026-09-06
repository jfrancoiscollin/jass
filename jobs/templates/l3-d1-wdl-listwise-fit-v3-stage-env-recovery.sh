#!/usr/bin/env bash
# D1 runtime compatibility entrypoint after 1846/1847 stage-env failures.
#
# run_experiment_stage.py deliberately sanitizes the stage environment and does
# not propagate EXPECTED_CODE_SHA. The historical D1 template still consumes
# that variable as a defence-in-depth assertion. Reconstruct it only from the
# already-authenticated immutable stage spec, verify it against HEAD, then exec
# the unchanged v2 D1 scientific template.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_STAGE_SPEC:?}"
cd "$JASS_CODE_DIR"

SPEC_CODE_SHA=$(python3 - "$JASS_STAGE_SPEC" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    value = json.loads(path.read_text(encoding="ascii"))
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"D1 stage spec unreadable: {exc}") from exc
sha = value.get("code_sha") if isinstance(value, dict) else None
if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
    raise SystemExit("D1 stage spec code_sha missing/invalid")
print(sha)
PY
)
HEAD_SHA=$(git rev-parse HEAD)
if [ "$HEAD_SHA" != "$SPEC_CODE_SHA" ]; then
  echo "D1 stage/spec code mismatch: head=$HEAD_SHA spec=$SPEC_CODE_SHA" >&2
  exit 64
fi

export EXPECTED_CODE_SHA="$SPEC_CODE_SHA"
exec /usr/bin/bash jobs/templates/l3-d1-wdl-listwise-fit-v2-historical-split.sh
