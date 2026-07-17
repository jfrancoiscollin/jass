#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Fail-closed launcher for the bounded ADJ+G1 probe next tours (T2 or T3).
#
# Required:
#   TOUR=T2|T3
#   PROBE_PARENT_RUN_PREFIX=r2:.../runs/<job>/<attempt>
#
# The core native launcher keeps the T1-bis scientific recipe unchanged.
# fetch_t1bis_inputs.py replaces only parent.pjtw.gz after verifying the
# previous runner-v3 result and its promotion_decision=promote/continue_probe.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${TOUR:?set TOUR=T2 or TOUR=T3}"
: "${PROBE_PARENT_RUN_PREFIX:?set previous promoted runner-v3 result prefix}"

case "$TOUR" in
  T2|T3) ;;
  *) echo "ABORT: next-tour launcher only accepts T2 or T3" >&2; exit 2 ;;
esac

cd "$JASS_CODE_DIR"
export TOUR PROBE_PARENT_RUN_PREFIX

# PrivateTmp/oneshot belt-and-suspenders guard.
export TMPDIR="${TMPDIR:-$JASS_RESULT_DIR/tmp}"
mkdir -p "$TMPDIR"

# Pre-engaged scientific totals and G1 position quota: unchanged from 0756.
export GYM_MIN_POS="${GYM_MIN_POS:-150}"
export MIN_PROTECTED_TIP_RATE="${MIN_PROTECTED_TIP_RATE:-0.0}"
export ALLOW_MTC_SKIP="${ALLOW_MTC_SKIP:-1}"
export NSH_GEN_TOTAL="${NSH_GEN_TOTAL:-8}"
export NSH_RELABEL_TOTAL="${NSH_RELABEL_TOTAL:-8}"
export NSH_CONV_TOTAL="${NSH_CONV_TOTAL:-4}"
export NSH_GATE_TOTAL="${NSH_GATE_TOTAL:-4}"

# ccx33 16 GiB operational concurrency caps; not scientific parameters.
export PAR_GEN="${PAR_GEN:-8}"
export PAR_RELABEL="${PAR_RELABEL:-8}"
export PAR_CONV="${PAR_CONV:-4}"
export PAR_GATE="${PAR_GATE:-4}"
export JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
export CACHE_MB_RELABEL="${CACHE_MB_RELABEL:-384}"
export CACHE_MB_CONV="${CACHE_MB_CONV:-192}"

exec bash jobs/templates/t1bis-adj-g1-runner-v3-native.sh
