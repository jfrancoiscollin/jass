#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"
export PYTHONPATH="$JASS_CODE_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/bash "$JASS_CODE_DIR/jobs/templates/l3-d4c-rank-breaker-micro-screen-v1.sh"
