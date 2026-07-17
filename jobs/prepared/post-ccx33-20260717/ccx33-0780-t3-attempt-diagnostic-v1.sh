#!/usr/bin/env bash
# id: ccx33-0780-t3-attempt-diagnostic-v1
# description: classify the later T3 exit -1 without replaying successful science
# expected_duration: <10 min; fill FAILED_RUN_PREFIX before enqueue
set -Eeuo pipefail
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export SUCCESS_RUN_PREFIX="${JASS_OBJSTORE_REMOTE%/}/runs/ccx33-0769-probe-t3-adj-g1-v1/20260717T145848Z-1b907771"
: "${T3_FAILED_RUN_PREFIX:?set the exact _FAILED runner-v3 prefix}"
export FAILED_RUN_PREFIX="$T3_FAILED_RUN_PREFIX"
exec bash jobs/templates/attempt-diagnostic-runner-v3.sh
