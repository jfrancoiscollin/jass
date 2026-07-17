#!/usr/bin/env bash
# id: cpx62-0774-forkc-c0-v1
# description: C0 fork-c weak-vs-strong + shared-T1-corpus refit + hard-conversion gate
# expected_duration: 1-3 h
set -Eeuo pipefail
: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
export TMPDIR="$JASS_RESULT_DIR/tmp"; mkdir -p "$TMPDIR"
export FORKC_WEAK_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/forkc-weak-v1"
export FORKC_STRONG_INPUTS_PREFIX="${JASS_OBJSTORE_REMOTE%/}/inputs/t1bis-adj-g1/v1"
export FORKC_BASELINE_RUN_PREFIX="${JASS_OBJSTORE_REMOTE%/}/runs/ccx33-0756-t1bis-adj-g1-native-full-v2/20260717T074749Z-6d90e72d"
export NSH_GATE_TOTAL=4 NSH_CONV_TOTAL=4
export PAR_GATE=4 PAR_CONV=4 JASS_BUILD_JOBS=8
export CACHE_MB_RELABEL=384
export MIN_POLICY_DIVERGENCE=0.05 MIN_HARD_DELTA=0.02
exec bash jobs/templates/forkc-c0-runner-v3.sh
