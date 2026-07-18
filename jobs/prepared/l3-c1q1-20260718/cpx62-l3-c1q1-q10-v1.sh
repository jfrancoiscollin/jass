#!/usr/bin/env bash
# id: cpx62-l3-c1q1-q10-v1
# description: L3-PURE C1-Q1 Q10_THREAT, captures + extension de menace
# expected_duration: pending per-box micro-calibration; do not queue without explicit go
set -Eeuo pipefail
export ARM=A
export FRONTIER_FRAC=0
export L3_VARIANT=Q10_THREAT
export L3_SEARCH_OVERRIDES="qs_threat_ext=1,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
export NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8
export BASE_SEED=271828
export SHARD_TIMEOUT=21600
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-pure-runner-v4.sh
