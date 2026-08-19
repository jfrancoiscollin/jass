#!/usr/bin/env bash
# Technical-only launcher for the preregistered CTX3 decision-flip autopsy.
# The merged v1 template contains transport artefacts: literal standalone '+'
# argv tokens followed by spacing where shell line continuations were intended.
# This launcher removes only those standalone '+' tokens. It does not alter any
# scientific constant, source identity, pool/model hash, depth, seed, bootstrap,
# classification threshold, frozen/promotion guard, or analysis code.
set -Eeuo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/l3-context3-decision-flip-autopsy-v1.sh"
TMP="$(mktemp "${TMPDIR:-/tmp}/jass-ctx3-autopsy.XXXXXX.sh")"
trap 'rm -f "$TMP"' EXIT

python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import re, sys
src, dst = map(Path, sys.argv[1:3])
text = src.read_text(encoding="utf-8")
# Only strip a standalone '+' shell argv token when it is outside heredoc Python
# and followed by at least two spaces before the next option/command token.
# This exact corruption pattern is present in the merged template.
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
exec bash "$TMP"
