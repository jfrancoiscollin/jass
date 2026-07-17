#!/usr/bin/env bash
# id: cpx62-0775-forkc-t1-v1
# description: T1 fork-c weak bootstrap, guarded by parent/fixed + absolute strong T0
# expected_duration: 2-4 h; enqueue only after 0774 scientific_status=proceed_t1
set -Eeuo pipefail
: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export TOUR=T1-bis
export T1BIS_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/forkc-weak-v1"
export ABSOLUTE_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export REQUIRE_ABSOLUTE_REFERENCE=1
export GYM_MIN_POS=150 MIN_PROTECTED_TIP_RATE=0.0 ALLOW_MTC_SKIP=1
export NSH_GEN_TOTAL=8 NSH_RELABEL_TOTAL=8 NSH_CONV_TOTAL=4 NSH_GATE_TOTAL=4
export PAR_GEN=8 PAR_RELABEL=8 PAR_CONV=4 PAR_GATE=4 JASS_BUILD_JOBS=8
export CACHE_MB_RELABEL=384 CACHE_MB_CONV=192
exec bash jobs/templates/t1bis-adj-g1-runner-v3-native.sh
