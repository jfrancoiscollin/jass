#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"

cd "$JASS_CODE_DIR"
SRC="jobs/templates/l3-d4-search-utility-offline-v1.sh"
TMP="$JASS_RESULT_DIR/d4-search-utility-offline-cardinality-recovery-stage.sh"

python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")
old = "grep -cve '^[[:space:]]*$' \"$W/d4-root-candidates.fen\""
new = "grep -cvE '^[[:space:]]*(#|$)' \"$W/d4-root-candidates.fen\""
if text.count(old) != 1:
    raise SystemExit(f"D4 recovery patch contract drift: expected exactly one cardinality guard, got {text.count(old)}")
patched = text.replace(old, new)
if old in patched or patched.count(new) != 1:
    raise SystemExit("D4 recovery patch did not apply exactly once")
out.write_text(patched, encoding="utf-8")
PY

exec /usr/bin/bash "$TMP"
