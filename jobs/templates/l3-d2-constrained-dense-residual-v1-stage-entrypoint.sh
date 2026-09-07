#!/usr/bin/env bash
# Reconstruct EXPECTED_CODE_SHA from the already-authenticated stage spec.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
cd "$JASS_CODE_DIR"
SPEC_CODE_SHA=$(python3 - "$JASS_STAGE_SPEC" <<'PY'
import json,re,sys
from pathlib import Path
p=Path(sys.argv[1])
try: v=json.loads(p.read_text(encoding='ascii'))
except Exception as exc: raise SystemExit(f'D2 stage spec unreadable: {exc}')
sha=v.get('code_sha') if isinstance(v,dict) else None
if not isinstance(sha,str) or re.fullmatch(r'[0-9a-f]{40}',sha) is None:
    raise SystemExit('D2 stage spec code_sha missing/invalid')
print(sha)
PY
)
HEAD_SHA=$(git rev-parse HEAD)
[ "$HEAD_SHA" = "$SPEC_CODE_SHA" ] || { echo "D2 stage/spec code mismatch: head=$HEAD_SHA spec=$SPEC_CODE_SHA" >&2; exit 64; }
export EXPECTED_CODE_SHA="$SPEC_CODE_SHA"
exec /usr/bin/bash jobs/templates/l3-d2-constrained-dense-residual-v1.sh
