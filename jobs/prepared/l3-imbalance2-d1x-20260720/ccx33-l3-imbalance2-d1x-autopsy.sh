#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-d1x-autopsy
# description: read-only RC4 feature/weight/stratum/generalist autopsy after D1 no-go
# do not queue without explicit go and a reviewed merged EXPECTED_CODE_SHA
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
export P1_PREFIX="r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d"
export EXPECTED_P1_JOB_ID="ccx33-0852-l3-imbalance2-role-v2-p1"
export D1_PREFIX="r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c"
export EXPECTED_D1_JOB_ID="cpx62-0872-l3-imbalance2-d1-rc4"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 D1X_AUTOPSY_GO=1
export JASS_BUILD_JOBS=8

exec bash jobs/templates/l3-imbalance2-d1x-autopsy-v1.sh
