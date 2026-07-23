#!/usr/bin/env bash
# id: cpx62-0920-salvage-0908-stable-top3-matrix-v1
# description: no-replay, single-cap adjudicated analysis of failed 0908
# expected_duration: 2-5 min on measured cpx62 nproc=16; hard cap 10 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed develop SHA containing the salvage tool}"
export EXPECTED_JOB_ID="cpx62-0920-salvage-0908-stable-top3-matrix-v1"
export SOURCE_0908_PREFIX="r2:jass-data/runs/cpx62-0908-l3-top3-stable-conversion-matrix-v1/20260723T131042Z-e4f1b5f7"
export SOURCE_0908_JOB_ID="cpx62-0908-l3-top3-stable-conversion-matrix-v1"
export SOURCE_0908_ATTEMPT_ID="20260723T131042Z-e4f1b5f7"
export SOURCE_0908_CODE_SHA="e4f1b5f74df637e41c000906d1852fd3b7a41005"
export SOURCE_PARTIAL_TAR_SHA256="9fa4bedd93df491bd0a46828dd5da30abf74fd53b116354869d453d70f2a5277"
export EXPECTED_CAP_ARM="g4_g4"
export EXPECTED_CAP_POSITION_ID="5caae5749ee56f08fba806798ed5499f45b8755209ab665fb0d36bd1605403c6"
export EXPECTED_CAP_CELL="18v20|adv=B|stm=W"
export SALVAGE_GO=1 NO_REPLAY=1 NO_AUTOMATIC_CONTINUATION=1
export BOOTSTRAP=10000 BOOTSTRAP_SEED=271828
exec timeout -k 30s 600s \
  bash jobs/templates/salvage-stable-conversion-matrix-v1.sh
