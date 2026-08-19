#!/usr/bin/env bash
# Technical-only launcher for the preregistered CTX3 decision-flip autopsy.
# Removes only transport-corruption '+' argv tokens and, on failure, exposes a
# sanitized diagnostic marker through the normal certified artefact manifest.
# Scientific constants, identities, depths, seeds, bootstrap and criteria stay untouched.
set -Eeuo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/l3-context3-decision-flip-autopsy-v1.sh"
TMP="$(mktemp "${TMPDIR:-/tmp}/jass-ctx3-autopsy.XXXXXX.sh")"
ERR="$(mktemp "${TMPDIR:-/tmp}/jass-ctx3-autopsy.err.XXXXXX")"
trap 'rm -f "$TMP" "$ERR"' EXIT

python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import re, sys
src, dst = map(Path, sys.argv[1:3])
text = src.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)
in_heredoc = False
out = []
for line in lines:
    if not in_heredoc:
        line = re.sub(r"(?<=\s)\+\s{2,}", " ", line)
    if "<<'PY'" in line:
        in_heredoc = True
    elif in_heredoc and line.rstrip("\n") == "PY":
        in_heredoc = False
    out.append(line)
fixed = "".join(out)
if fixed == text:
    raise SystemExit("runtimefix: expected shell corruption pattern not found")
if re.search(r"(?m)(?<!\S)\+\s{2,}", fixed):
    raise SystemExit("runtimefix: standalone plus transport artefact remains")
dst.write_text(fixed, encoding="utf-8")
PY

bash -n "$TMP"
set +e
bash "$TMP" 2> >(tee "$ERR" >&2)
rc=$?
set -e
if [ "$rc" -ne 0 ] && [ -n "${JASS_ARTEFACT_DIR:-}" ]; then
  mkdir -p "$JASS_ARTEFACT_DIR"
  diag="$(tail -n 4 "$ERR" 2>/dev/null | tr '\n' ' ' | sed -E 's/[^A-Za-z0-9._=-]+/_/g' | cut -c1-180)"
  [ -n "$diag" ] || diag="rc_${rc}_no_stderr"
  touch "$JASS_ARTEFACT_DIR/TECHFAIL__RC_${rc}__${diag}"
fi
exit "$rc"
