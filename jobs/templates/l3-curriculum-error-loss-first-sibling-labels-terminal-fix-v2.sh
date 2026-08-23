#!/usr/bin/env bash
# Technical wrapper: route only loss-first label-worker calls through the
# terminal-child adapter. Every other command is byte-for-byte the base path.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"
JASS_REAL_PYTHON3="$(command -v python3)"
export JASS_REAL_PYTHON3
python3() {
  if [ "${1:-}" = "jobs/tools/l3_curriculum_error_loss_first_sibling_labels.py" ] \
     && [ "${2:-}" = "label-worker" ]; then
    shift
    "$JASS_REAL_PYTHON3" -m jobs.tools.l3_curriculum_error_loss_first_sibling_labels_terminal_fix "$@"
  else
    "$JASS_REAL_PYTHON3" "$@"
  fi
}
export -f python3
exec bash jobs/templates/l3-curriculum-error-loss-first-sibling-labels-v1.sh
