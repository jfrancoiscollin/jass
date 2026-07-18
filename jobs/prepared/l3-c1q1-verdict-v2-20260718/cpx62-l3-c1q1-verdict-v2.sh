#!/usr/bin/env bash
# id: cpx62-l3-c1q1-verdict-v2
# description: corrected C1-Q1 evaluation only; reuses Q00/Q10/Q01/Q11 G2
# expected_duration: pending calibration; do not queue without Claude review + JFC go
# GitOps must export EXPECTED_CODE_SHA to the reviewed merge commit.
set -Eeuo pipefail
export NOPEN=300 NSH_GATE=16 PAR_GATE=5
export NSH_CONV=8 PAR_CONV=4
export DEPTH=9 CONV_DEPTH=10 ARB_DEPTH=14
export NATIVE_MOVETIME=0.1 BOOTSTRAP_REPLICATES=10000
export SHARD_TIMEOUT=7200 CACHE_MB=128 JASS_BUILD_JOBS=8
export SCREEN_DELTA=0.02
exec bash jobs/templates/l3-c1q1-verdict-v2.sh
