#!/usr/bin/env bash
# id: smoke-develop-object-store
# description: validate develop-pinned worktree, control claim and result publication
set -euo pipefail
cd "$JASS_CODE_DIR"
mkdir -p "$JASS_ARTEFACT_DIR"
printf 'job=%s\nattempt=%s\ncode_dir=%s\n' \
  "$JASS_JOB_ID" "$JASS_ATTEMPT_ID" "$JASS_CODE_DIR" \
  > "$JASS_ARTEFACT_DIR/smoke.txt"
git rev-parse HEAD > "$JASS_ARTEFACT_DIR/code_sha.txt"
test "$(git branch --show-current)" = ""
