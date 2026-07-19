#!/usr/bin/env bash
# id: cpx62-l3-p1-frozen-v1
# description: L3-PURE P1 frozen baseline, fresh G1-G4 from material G0 on cpx62
# expected_duration: about 45-60 min from prior cpx62 throughput; verify disk before queue
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set to the merged jass SHA in the jass-control job}"
export FULL_RUN_APPROVED=1
export SCIENTIFIC_GO=1
export FRONTIER_FRAC=0
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
export NGEN=4 FRESH=500000 NSHARDS=8 PAR_GEN=8 PLAY_DEPTH=8
export MAXPLIES=260 LABEL_DEPTH=4
export RANDOM_OPEN_PLIES=8 EXPLORE_EPS=8 EXPLORE_DECAY_PLIES=60
export HOLDOUT_MOD=10 BASE_SEED=271828
export L2=3e-5 MAXIT=25 CHUNK=500000
export SHARD_TIMEOUT=21600 JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-pure-p1-runner-v1.sh
