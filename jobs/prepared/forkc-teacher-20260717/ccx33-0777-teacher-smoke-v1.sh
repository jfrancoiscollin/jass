#!/usr/bin/env bash
# id: ccx33-0777-teacher-smoke-v1
# description: matched A/B1/B2/B3 conversion teacher smoke; requires successful 0776 corpus
# expected_duration: 3-6 h
set -Eeuo pipefail
: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${TEACHER_CORPUS_RUN_PREFIX:?set to completed 0776 result URI before enqueue}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export SOURCE_RUN_PREFIX="${JASS_OBJSTORE_REMOTE%/}/runs/ccx33-0769-probe-t3-adj-g1-v1/20260717T145848Z-1b907771"
export STRONG_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export MIN_TEACHER_PARENTS=50
export NSH_GATE_TOTAL=4 NSH_CONV_TOTAL=4
export PAR_GATE=4 PAR_CONV=4 JASS_BUILD_JOBS=8
export CACHE_MB_RELABEL=384
export MIN_HARD_DELTA=0.02 SIMPLICITY_TOLERANCE=0.005
exec bash jobs/templates/conversion-teacher-smoke-runner-v3.sh
