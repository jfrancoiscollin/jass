#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-top3-selfplay-p1
# description: P1 G1-G4 d8 trained only from 16v18, 17v19 and 18v20 self-play, then paired G0/G4 evaluation
# expected_duration: 8-16 h on ccx33
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA in jass-control}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1
export FRESH=500000 PAR_GEN=6 MAXPLIES=260 LABEL_DEPTH=4 PLAY_DEPTH=8
export RANDOM_OPEN_PLIES=8 EXPLORE_EPS=8 EXPLORE_DECAY_PLIES=60
export HOLDOUT_MOD=10 BASE_SEED=271828 MAXIT=25 L2=3e-5 CHUNK=500000
export TRAIN_SEEDS_PER_SIDE=2048 EVAL_PER_STRATUM=64 EVAL_SHARDS=6 PAR_EVAL=4
export WIN_WEIGHT=1 DRAW_WEIGHT=2 LOSS_WEIGHT=4
export JASS_BUILD_JOBS=8
export L3_SEARCH_OVERRIDES="qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0"
exec bash jobs/templates/l3-imbalance2-top3-selfplay-v1.sh
