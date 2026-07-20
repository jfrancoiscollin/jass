#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-role-v2-p3
# description: ccx33 P3 d12; immutable P2 parent; same independent A64/B64 pools
# expected_duration: pending ccx33 calibration; do not queue without explicit go
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA}"
: "${PARENT_MODEL_URI:?set immutable previous phase final model URI/path}"
: "${PARENT_MODEL_SHA256:?set previous phase final model gzip SHA256}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 PHASE=P3
export FRESH=500000 NSHARDS=18 PAR_GEN=8 MAXPLIES=260 LABEL_DEPTH=4
export RANDOM_OPEN_PLIES=8 EXPLORE_EPS=8 EXPLORE_DECAY_PLIES=60
export HOLDOUT_MOD=10 BASE_SEED=271828 MAXIT=25 L2=3e-5 CHUNK=500000
export TRAIN_SEEDS_PER_SIDE=2048 BENCH_PER_STRATUM=24 PLATEAU_PER_STRATUM=64 FRONTIER_FRAC=0
export IMBALANCE2_PLATEAU_SEED=161803
export WIN_WEIGHT=1 DRAW_WEIGHT=2 LOSS_WEIGHT=4
export JASS_BUILD_JOBS=8
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
exec bash jobs/templates/l3-imbalance2-runner-v2.sh
