#!/usr/bin/env bash
# id: ccx33-0776-teacher-mine-t3-v1
# description: mine T3 causal WIN->DRAW/LOSS and materialize matched B1/B2/B3 corpus
# expected_duration: 1-3 h
set -Eeuo pipefail
: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export SOURCE_RUN_PREFIX="${JASS_OBJSTORE_REMOTE%/}/runs/ccx33-0769-probe-t3-adj-g1-v1/20260717T145848Z-1b907771"
export PROBE_TOUR=T3
export ARB_DEPTH=14 LEAF_DEPTH=9 CACHE_MB_RELABEL=384
export HOLDOUT_MOD=5 MAX_SIBLINGS_PER_PARENT=4 JASS_BUILD_JOBS=8
exec bash jobs/templates/conversion-teacher-mine-runner-v3.sh
