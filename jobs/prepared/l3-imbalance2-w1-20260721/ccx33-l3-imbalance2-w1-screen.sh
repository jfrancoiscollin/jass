#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-w1-adaptive-screen
# description: weight-only W1 screen, fixed 1/2/4 control vs W0 stratum-adaptive candidate
# do not queue without reviewed merged EXPECTED_CODE_SHA
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set reviewed merged jass SHA}"
export P1_PREFIX="r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d"
export EXPECTED_P1_JOB_ID="ccx33-0852-l3-imbalance2-role-v2-p1"
export W0_PREFIX="r2:jass-data/runs/cpx62-0877-l3-imbalance2-w0-oracle-calibration/20260720T235638Z-d0329285"
export EXPECTED_W0_JOB_ID="cpx62-0877-l3-imbalance2-w0-oracle-calibration"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 W1_ADAPTIVE_GO=1
export POOL_SEED=141421 PLATEAU_PER_STRATUM=64
export DEPTH=10 MAXPLIES=400 NSHARDS=8 PAR=8
export BOOTSTRAP=10000 HOLDOUT_MOD=10 BASE_SEED=271828 RESAMPLE_SEED=271832
export L2=3e-5 MAXIT=25 CHUNK=500000 JASS_BUILD_JOBS=8 GENERALIST_PAIRS=64

exec bash jobs/templates/l3-imbalance2-w1-screen-v1.sh
