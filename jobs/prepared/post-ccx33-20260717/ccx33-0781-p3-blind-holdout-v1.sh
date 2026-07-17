#!/usr/bin/env bash
# id: ccx33-0781-p3-blind-holdout-v1
# description: build a powered fresh P3/P4 holdout blind to the teacher winner
# expected_duration: 1-3 h; enqueue only after 0777 decision=confirm
set -Eeuo pipefail
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
: "${TEACHER_SMOKE_RUN_PREFIX:?set exact completed 0777 prefix}"
: "${MTC_AUDIT_RUN_PREFIX:?set exact completed ccx33-0778 prefix}"
export STRONG_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export JASS_EGDB_PATH=/root/egdb_extracted/app
export JASS_EGDB_MTC_PATH=/root/egdb_mtc/app
export HOLDOUT_GAMES=12000 HOLDOUT_SEED=77801
export NSH_GEN_TOTAL=8 PAR_GEN=8 JASS_BUILD_JOBS=8 CACHE_MB_RELABEL=384
export MIN_P3_DELTA=0.02 P3_TARGET_POWER=0.80 P3_ALPHA=0.05
exec bash jobs/templates/p3-blind-holdout-runner-v3.sh
