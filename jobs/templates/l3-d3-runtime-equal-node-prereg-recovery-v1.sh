#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ORIGINAL="$ROOT/jobs/templates/l3-d3-runtime-equal-node-v1.sh"
BROKEN="grep -Fq '20,000' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md"
FIXED="grep -Fq '20000 nodes per move each arm' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md"

render_recovered_stage() {
  local src="$1" dst="$2"
  python3 - "$src" "$dst" "$BROKEN" "$FIXED" <<'PY'
from pathlib import Path
import sys
src, dst, broken, fixed = sys.argv[1:]
text = Path(src).read_text(encoding="utf-8")
if text.count(broken) != 1:
    raise SystemExit("D3 equal-node prereg recovery anchor drift")
if fixed in text:
    raise SystemExit("D3 equal-node prereg recovery unexpectedly already applied")
Path(dst).write_text(text.replace(broken, fixed, 1), encoding="utf-8")
PY
}

if [[ "${1:-}" == "--self-test" ]]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  render_recovered_stage "$ORIGINAL" "$tmp/recovered.sh"
  /usr/bin/grep -Fq "$FIXED" "$tmp/recovered.sh"
  ! /usr/bin/grep -Fq "$BROKEN" "$tmp/recovered.sh"

  python3 - "$ORIGINAL" "$tmp/drifted.sh" "$BROKEN" <<'PY'
from pathlib import Path
import sys
src, dst, broken = sys.argv[1:]
text = Path(src).read_text(encoding="utf-8")
if text.count(broken) != 1:
    raise SystemExit("self-test source anchor drift")
Path(dst).write_text(text.replace(broken, broken.replace("20,000", "20.000"), 1), encoding="utf-8")
PY
  if render_recovered_stage "$tmp/drifted.sh" "$tmp/should-not-exist.sh" 2>/dev/null; then
    echo "recovery renderer did not fail closed on anchor drift" >&2
    exit 1
  fi
  exit 0
fi

: "${JASS_RESULT_DIR:?}"
TMP_STAGE=$(mktemp "$JASS_RESULT_DIR/d3-equal-node-recovered-stage.XXXXXX.sh")
render_recovered_stage "$ORIGINAL" "$TMP_STAGE"
chmod 0700 "$TMP_STAGE"
exec /usr/bin/bash "$TMP_STAGE"
