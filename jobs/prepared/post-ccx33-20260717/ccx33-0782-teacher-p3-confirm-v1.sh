#!/usr/bin/env bash
# id: ccx33-0782-teacher-p3-confirm-v1
# description: powered blind P3 confirmation of the single 0777 winner
# expected_duration: 4-10 h; enqueue only after 0781 decision=ready
set -Eeuo pipefail
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
: "${TEACHER_SMOKE_RUN_PREFIX:?set exact completed 0777 prefix}"
: "${P3_HOLDOUT_RUN_PREFIX:?set exact ready ccx33-0781 prefix}"
: "${MTC_AUDIT_RUN_PREFIX:?set exact completed ccx33-0778 prefix}"
export STRONG_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export JASS_EGDB_PATH=/root/egdb_extracted/app
export JASS_EGDB_MTC_PATH=/root/egdb_mtc/app
export NSH_CONV_TOTAL=8 PAR_CONV=8 NSH_GATE_TOTAL=8 PAR_GATE=8
export NOPEN=600 PAIRS=2 JASS_BUILD_JOBS=8 CACHE_MB_RELABEL=384
export MIN_P3_DELTA=0.02 P4_NON_REGRESSION_MARGIN=0.02
export P3_TARGET_POWER=0.80 P3_ALPHA=0.05
exec bash jobs/templates/conversion-teacher-confirm-runner-v3.sh
