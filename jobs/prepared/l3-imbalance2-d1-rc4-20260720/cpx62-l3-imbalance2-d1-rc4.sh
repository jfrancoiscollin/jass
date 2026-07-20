#!/usr/bin/env bash
# id: cpx62-l3-imbalance2-d1-rc4
# description: D1-A RC4 same-corpus representation screen; no new training self-play
# do not queue without explicit go and a reviewed merged EXPECTED_CODE_SHA
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
export P1_PREFIX="r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d"
export EXPECTED_P1_JOB_ID="ccx33-0852-l3-imbalance2-role-v2-p1"
export D0_PREFIX="r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7"
export EXPECTED_D0_JOB_ID="cpx62-0871-l3-imbalance2-d0-diagnostic"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 D1_RC4_GO=1
export POOL_SEED=314159 PLATEAU_PER_STRATUM=64 DEPTH=10 MAXPLIES=400
export NSHARDS=8 PAR=8 SENTINEL_SHARDS=4 SHARD_TIMEOUT=21600 BOOTSTRAP=10000
export HOLDOUT_MOD=10 BASE_SEED=271828 L2=3e-5 MAXIT=25 CHUNK=500000
export JASS_BUILD_JOBS=8 GENERALIST_PAIRS=64

exec bash jobs/templates/l3-imbalance2-d1-rc4-v1.sh
