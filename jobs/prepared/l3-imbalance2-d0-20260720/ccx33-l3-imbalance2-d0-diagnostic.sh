#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-d0-diagnostic
# description: D0 causal diagnostic on immutable G4/G8 A64/B64 artefacts; static searches only
# do not queue without explicit go and a merged EXPECTED_CODE_SHA
set -Eeuo pipefail

: "${EXPECTED_CODE_SHA:?set the reviewed merged jass SHA}"
: "${SCAN_BIN:?path to the reviewed Scan binary}"
export P1_PREFIX="r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d"
export P2_PREFIX="r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238"
export P1_RAW_PREFIX="r2:jass-data/runs/ccx33-0853-l3-imbalance2-p1-v1-v2-a64-compare/20260720T083743Z-61839d1d"
export P2_RAW_PREFIX="r2:jass-data/runs/ccx33-0864-l3-imbalance2-role-v2-p2-plateau/20260720T135748Z-59940065"
export REFERENCE_PREFIX="r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065"
export EXPECTED_P1_JOB_ID="ccx33-0852-l3-imbalance2-role-v2-p1"
export EXPECTED_P2_JOB_ID="ccx33-0859-l3-imbalance2-role-v2-p2"
export EXPECTED_P1_RAW_JOB_ID="ccx33-0853-l3-imbalance2-p1-v1-v2-a64-compare"
export EXPECTED_P2_RAW_JOB_ID="ccx33-0864-l3-imbalance2-role-v2-p2-plateau"
export EXPECTED_REFERENCE_JOB_ID="cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 D0_DIAGNOSTIC_GO=1
export DEPTHS="8,10,12,14" NSHARDS=8 PAR=8 SHARD_TIMEOUT=21600 JASS_BUILD_JOBS=8
export SENTINELS=30 PER_FAMILY=10 PLATEAU_PER_STRATUM=64 PLATEAU_SEED=161803
export MAX_EXCLUDED_POSITIONS=2 MAX_EXCLUDED_FRACTION=0.001 SCAN_BB_SIZE=0

exec bash jobs/templates/l3-imbalance2-d0-diagnostic-v1.sh
