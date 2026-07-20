#!/usr/bin/env bash
# id: cpx62-l3-imbalance2-w0-oracle-calibration
# expected_duration: ~3-8 min on cpx62; read-only, no training
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; cd "$JASS_CODE_DIR"
: "${EXPECTED_CODE_SHA:?queue job must pin merged develop SHA}"
export W0_CALIBRATION_GO=1
export DIFFICULTY_REFERENCE_URI="r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065"
exec bash jobs/templates/l3-imbalance2-w0-oracle-calibration-v1.sh
