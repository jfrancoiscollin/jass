#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-seed-clean-screen-v1
# description: one-generation TOP3 screen with exact seed sampling, quiet WDL and no random play
# expected_duration: pending ccx33 preflight; target 30-60 min
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA in jass-control}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export SEED_CLEAN=1 GENERATIONS=1 FRESH=100000 PAR_GEN=6
export MAXPLIES=260 LABEL_DEPTH=4 PLAY_DEPTH=8
export RANDOM_OPEN_PLIES=0 EXPLORE_EPS=0 EXPLORE_DECAY_PLIES=0
export HOLDOUT_MOD=10 BASE_SEED=271828 MAXIT=25 L2=3e-5 CHUNK=500000
export TRAIN_SEEDS_PER_SIDE=2048 EVAL_PER_STRATUM=64 EVAL_SHARDS=6 PAR_EVAL=4
export WIN_WEIGHT=1 DRAW_WEIGHT=1 LOSS_WEIGHT=1
export GEN_SHARD_TIMEOUT=1800 EVAL_SHARD_TIMEOUT=3600 JASS_BUILD_JOBS=8
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
exec bash jobs/templates/l3-imbalance2-top3-selfplay-v1.sh
