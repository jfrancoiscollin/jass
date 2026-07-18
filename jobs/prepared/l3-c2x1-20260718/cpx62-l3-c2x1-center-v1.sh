#!/usr/bin/env bash
# id: cpx62-l3-c2x1-center-v1
# description: L3-PURE C2-X1 curvature centre (open=6, epsilon=6%, decay=45)
# expected_duration: pending exact-profile micro-calibration; do not queue without explicit go
set -Eeuo pipefail
export ARM=A
export FRONTIER_FRAC=0
export L3_VARIANT=X_CENTER
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
export RANDOM_OPEN_PLIES=6 EXPLORE_EPS=6 EXPLORE_DECAY_PLIES=45
export NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8
export BASE_SEED=271828
export SHARD_TIMEOUT=21600
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-pure-x1-runner-v5.sh
