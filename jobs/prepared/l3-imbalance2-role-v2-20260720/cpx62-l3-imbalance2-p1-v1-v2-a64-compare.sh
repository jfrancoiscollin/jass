#!/usr/bin/env bash
# id: cpx62-l3-imbalance2-p1-v1-v2-a64-compare
# description: re-assess historical 0847 G1-G4 and role-V2 G1-G4 on common A64/B64 pools
# expected_duration: calibrate after V2 P1 completes; 18,432 candidate-only d10 games
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set reviewed merged jass SHA}"
: "${V1_P1_PREFIX:?set immutable completed result prefix for historical ccx33-0847 P1}"
: "${V2_P1_PREFIX:?set immutable completed result prefix for new role-aware V2 P1}"
: "${EXPECTED_V1_JOB_ID:?set exact historical source job id}"
: "${EXPECTED_V2_JOB_ID:?set exact role-aware source job id}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 COMPARISON_GO=1
export DEPTH=10 MAXPLIES=400 NSHARDS=8 PAR=8 SHARD_TIMEOUT=21600
export BOOTSTRAP=10000 PLATEAU_PER_STRATUM=64 PLATEAU_SEED=161803
export JASS_BUILD_JOBS=8
exec bash jobs/templates/l3-imbalance2-p1-compare-v1.sh
